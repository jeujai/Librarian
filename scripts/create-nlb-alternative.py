#!/usr/bin/env python3
"""
Create Network Load Balancer Alternative
=========================================

This script creates a Network Load Balancer (NLB) as an alternative to the
Application Load Balancer (ALB) for the multimodal-lib-prod application.

NLB uses Layer 4 (TCP) routing which is simpler and often more reliable than
ALB's Layer 7 (HTTP) routing.

Usage:
    python scripts/create-nlb-alternative.py

Requirements:
    - AWS CLI configured with appropriate credentials
    - boto3 library installed
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

# Configuration
VPC_ID = "vpc-0b2186b38779e77f6"
SUBNETS = [
    "subnet-0c352188f5398a718",  # us-east-1a
    "subnet-02f4d9ecb751beb27",  # us-east-1b
    "subnet-02fe694f061238d5a"   # us-east-1c
]
NLB_NAME = "multimodal-lib-prod-nlb"
TARGET_GROUP_NAME = "multimodal-lib-prod-nlb-tg"
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
CONTAINER_NAME = "multimodal-lib-prod-app"
CONTAINER_PORT = 8000

# Initialize AWS clients
elbv2_client = boto3.client('elbv2', region_name='us-east-1')
ecs_client = boto3.client('ecs', region_name='us-east-1')


def create_nlb_target_group() -> Dict[str, Any]:
    """
    Create NLB target group with TCP health checks.
    
    Returns:
        Dict containing target group details
    """
    print("\n" + "="*80)
    print("STEP 1: Creating NLB Target Group")
    print("="*80)
    
    try:
        response = elbv2_client.create_target_group(
            Name=TARGET_GROUP_NAME,
            Protocol='TCP',
            Port=CONTAINER_PORT,
            VpcId=VPC_ID,
            TargetType='ip',
            HealthCheckEnabled=True,
            HealthCheckProtocol='TCP',
            HealthCheckIntervalSeconds=30,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=2,
            Tags=[
                {'Key': 'Name', 'Value': TARGET_GROUP_NAME},
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'LoadBalancerType', 'Value': 'NLB'},
                {'Key': 'CreatedDate', 'Value': datetime.now().isoformat()}
            ]
        )
        
        target_group = response['TargetGroups'][0]
        target_group_arn = target_group['TargetGroupArn']
        
        print(f"✅ Target Group Created Successfully!")
        print(f"   Name: {target_group['TargetGroupName']}")
        print(f"   ARN: {target_group_arn}")
        print(f"   Protocol: {target_group['Protocol']}")
        print(f"   Port: {target_group['Port']}")
        print(f"   Health Check: TCP on port {CONTAINER_PORT}")
        
        return {
            'TargetGroupArn': target_group_arn,
            'TargetGroupName': target_group['TargetGroupName'],
            'Details': target_group
        }
        
    except Exception as e:
        print(f"❌ Error creating target group: {str(e)}")
        raise


def create_network_load_balancer() -> Dict[str, Any]:
    """
    Create Network Load Balancer.
    
    Returns:
        Dict containing NLB details
    """
    print("\n" + "="*80)
    print("STEP 2: Creating Network Load Balancer")
    print("="*80)
    
    try:
        response = elbv2_client.create_load_balancer(
            Name=NLB_NAME,
            Subnets=SUBNETS,
            Scheme='internet-facing',
            Type='network',
            IpAddressType='ipv4',
            Tags=[
                {'Key': 'Name', 'Value': NLB_NAME},
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Type', 'Value': 'network'},
                {'Key': 'CreatedDate', 'Value': datetime.now().isoformat()}
            ]
        )
        
        nlb = response['LoadBalancers'][0]
        nlb_arn = nlb['LoadBalancerArn']
        nlb_dns = nlb['DNSName']
        
        print(f"✅ Network Load Balancer Created Successfully!")
        print(f"   Name: {nlb['LoadBalancerName']}")
        print(f"   ARN: {nlb_arn}")
        print(f"   DNS: {nlb_dns}")
        print(f"   State: {nlb['State']['Code']}")
        print(f"   Type: {nlb['Type']}")
        print(f"   Scheme: {nlb['Scheme']}")
        
        # Wait for NLB to become active
        print("\n⏳ Waiting for NLB to become active...")
        waiter = elbv2_client.get_waiter('load_balancer_available')
        waiter.wait(LoadBalancerArns=[nlb_arn])
        print("✅ NLB is now active!")
        
        return {
            'LoadBalancerArn': nlb_arn,
            'LoadBalancerName': nlb['LoadBalancerName'],
            'DNSName': nlb_dns,
            'Details': nlb
        }
        
    except Exception as e:
        print(f"❌ Error creating NLB: {str(e)}")
        raise


def create_tcp_listener(nlb_arn: str, target_group_arn: str) -> Dict[str, Any]:
    """
    Create TCP listener for NLB.
    
    Args:
        nlb_arn: ARN of the Network Load Balancer
        target_group_arn: ARN of the target group
        
    Returns:
        Dict containing listener details
    """
    print("\n" + "="*80)
    print("STEP 3: Creating TCP Listener")
    print("="*80)
    
    try:
        response = elbv2_client.create_listener(
            LoadBalancerArn=nlb_arn,
            Protocol='TCP',
            Port=80,
            DefaultActions=[
                {
                    'Type': 'forward',
                    'TargetGroupArn': target_group_arn
                }
            ]
        )
        
        listener = response['Listeners'][0]
        listener_arn = listener['ListenerArn']
        
        print(f"✅ TCP Listener Created Successfully!")
        print(f"   ARN: {listener_arn}")
        print(f"   Protocol: {listener['Protocol']}")
        print(f"   Port: {listener['Port']}")
        print(f"   Target Group: {target_group_arn}")
        
        return {
            'ListenerArn': listener_arn,
            'Details': listener
        }
        
    except Exception as e:
        print(f"❌ Error creating listener: {str(e)}")
        raise


def update_ecs_service_with_nlb(target_group_arn: str) -> Dict[str, Any]:
    """
    Update ECS service to use NLB target group.
    
    Args:
        target_group_arn: ARN of the NLB target group
        
    Returns:
        Dict containing service update details
    """
    print("\n" + "="*80)
    print("STEP 4: Updating ECS Service with NLB")
    print("="*80)
    
    try:
        response = ecs_client.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            loadBalancers=[
                {
                    'targetGroupArn': target_group_arn,
                    'containerName': CONTAINER_NAME,
                    'containerPort': CONTAINER_PORT
                }
            ],
            healthCheckGracePeriodSeconds=300,
            forceNewDeployment=True
        )
        
        service = response['service']
        
        print(f"✅ ECS Service Updated Successfully!")
        print(f"   Service: {service['serviceName']}")
        print(f"   Cluster: {service['clusterArn'].split('/')[-1]}")
        print(f"   Status: {service['status']}")
        print(f"   Desired Count: {service['desiredCount']}")
        print(f"   Running Count: {service['runningCount']}")
        print(f"   Force New Deployment: True")
        
        return {
            'ServiceName': service['serviceName'],
            'Status': service['status'],
            'Details': service
        }
        
    except Exception as e:
        print(f"❌ Error updating ECS service: {str(e)}")
        raise


def monitor_target_health(target_group_arn: str, duration_seconds: int = 300) -> bool:
    """
    Monitor target health status.
    
    Args:
        target_group_arn: ARN of the target group
        duration_seconds: How long to monitor (default 5 minutes)
        
    Returns:
        True if targets become healthy, False otherwise
    """
    print("\n" + "="*80)
    print("STEP 5: Monitoring Target Health")
    print("="*80)
    
    print(f"⏳ Monitoring target health for up to {duration_seconds} seconds...")
    print("   Waiting for ECS task to register and become healthy...")
    
    start_time = time.time()
    check_interval = 10
    
    while time.time() - start_time < duration_seconds:
        try:
            response = elbv2_client.describe_target_health(
                TargetGroupArn=target_group_arn
            )
            
            targets = response['TargetHealthDescriptions']
            
            if not targets:
                print(f"   ⏳ No targets registered yet... (elapsed: {int(time.time() - start_time)}s)")
            else:
                for target in targets:
                    target_id = target['Target']['Id']
                    health_state = target['TargetHealth']['State']
                    reason = target['TargetHealth'].get('Reason', 'N/A')
                    
                    print(f"   Target: {target_id}")
                    print(f"   State: {health_state}")
                    print(f"   Reason: {reason}")
                    
                    if health_state == 'healthy':
                        print(f"\n✅ Target is HEALTHY!")
                        return True
                    elif health_state in ['draining', 'unavailable']:
                        print(f"   ⚠️  Target is {health_state}")
                    else:
                        print(f"   ⏳ Target is {health_state}")
            
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"   ⚠️  Error checking target health: {str(e)}")
            time.sleep(check_interval)
    
    print(f"\n⚠️  Timeout: Targets did not become healthy within {duration_seconds} seconds")
    return False


def verify_nlb_connectivity(nlb_dns: str) -> bool:
    """
    Verify NLB connectivity by testing the DNS endpoint.
    
    Args:
        nlb_dns: DNS name of the NLB
        
    Returns:
        True if connectivity test passes, False otherwise
    """
    print("\n" + "="*80)
    print("STEP 6: Verifying NLB Connectivity")
    print("="*80)
    
    import subprocess
    
    print(f"🔍 Testing NLB endpoint: http://{nlb_dns}/api/health/simple")
    
    try:
        # Test with curl
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 
             f'http://{nlb_dns}/api/health/simple'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        status_code = result.stdout.strip()
        
        if status_code == '200':
            print(f"✅ NLB Connectivity Test PASSED!")
            print(f"   Status Code: {status_code}")
            return True
        else:
            print(f"⚠️  NLB Connectivity Test returned: {status_code}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⚠️  NLB Connectivity Test timed out")
        return False
    except Exception as e:
        print(f"⚠️  NLB Connectivity Test failed: {str(e)}")
        return False


def save_results(results: Dict[str, Any], filename: str):
    """
    Save results to JSON file.
    
    Args:
        results: Results dictionary
        filename: Output filename
    """
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Results saved to: {filename}")


def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("NETWORK LOAD BALANCER CREATION")
    print("="*80)
    print(f"Creating NLB alternative for multimodal-lib-prod application")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'success': False,
        'steps': {}
    }
    
    try:
        # Step 1: Create target group
        tg_result = create_nlb_target_group()
        results['steps']['target_group'] = tg_result
        target_group_arn = tg_result['TargetGroupArn']
        
        # Step 2: Create NLB
        nlb_result = create_network_load_balancer()
        results['steps']['nlb'] = nlb_result
        nlb_arn = nlb_result['LoadBalancerArn']
        nlb_dns = nlb_result['DNSName']
        
        # Step 3: Create listener
        listener_result = create_tcp_listener(nlb_arn, target_group_arn)
        results['steps']['listener'] = listener_result
        
        # Step 4: Update ECS service
        service_result = update_ecs_service_with_nlb(target_group_arn)
        results['steps']['ecs_service'] = service_result
        
        # Step 5: Monitor target health
        health_ok = monitor_target_health(target_group_arn)
        results['steps']['target_health'] = {
            'healthy': health_ok,
            'checked_at': datetime.now().isoformat()
        }
        
        # Step 6: Verify connectivity
        connectivity_ok = verify_nlb_connectivity(nlb_dns)
        results['steps']['connectivity'] = {
            'success': connectivity_ok,
            'checked_at': datetime.now().isoformat()
        }
        
        # Overall success
        results['success'] = health_ok and connectivity_ok
        
        # Save results
        timestamp = int(time.time())
        filename = f"nlb-creation-{timestamp}.json"
        save_results(results, filename)
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        
        if results['success']:
            print("✅ NLB Creation SUCCESSFUL!")
            print(f"\n📋 Next Steps:")
            print(f"   1. Update CloudFront origin to: {nlb_dns}")
            print(f"   2. Test HTTPS URL: https://d3a2xw711pvw5j.cloudfront.net/")
            print(f"   3. Monitor for stability")
            print(f"   4. Clean up old ALB resources")
        else:
            print("⚠️  NLB Creation completed with warnings")
            print(f"\n📋 Issues:")
            if not health_ok:
                print(f"   - Targets not healthy yet (may need more time)")
            if not connectivity_ok:
                print(f"   - Connectivity test failed (may need more time)")
            print(f"\n💡 Recommendations:")
            print(f"   - Wait a few more minutes for tasks to stabilize")
            print(f"   - Check ECS service events for errors")
            print(f"   - Verify security groups allow NLB traffic")
        
        print(f"\n📊 NLB Details:")
        print(f"   Name: {NLB_NAME}")
        print(f"   DNS: {nlb_dns}")
        print(f"   Target Group: {TARGET_GROUP_NAME}")
        print(f"   Protocol: TCP")
        print(f"   Port: 80 → {CONTAINER_PORT}")
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        results['error'] = str(e)
        
        # Save error results
        timestamp = int(time.time())
        filename = f"nlb-creation-error-{timestamp}.json"
        save_results(results, filename)
        
        raise


if __name__ == '__main__':
    main()
