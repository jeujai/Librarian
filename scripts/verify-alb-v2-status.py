#!/usr/bin/env python3
"""
Verify the status of the newly created ALB v2 infrastructure.

This script checks all components of the new ALB setup to ensure
everything is configured correctly.
"""

import boto3
import json
import sys
from datetime import datetime
from typing import Dict, Any

def verify_alb() -> Dict[str, Any]:
    """Verify ALB status."""
    client = boto3.client('elbv2', region_name='us-east-1')
    
    print("=" * 80)
    print("Verifying Application Load Balancer")
    print("=" * 80)
    
    try:
        response = client.describe_load_balancers(
            Names=['multimodal-lib-prod-alb-v2']
        )
        
        if not response['LoadBalancers']:
            print("❌ ALB not found!")
            return {'success': False, 'error': 'ALB not found'}
        
        alb = response['LoadBalancers'][0]
        
        print(f"\n✅ ALB Found: {alb['LoadBalancerName']}")
        print(f"   ARN: {alb['LoadBalancerArn']}")
        print(f"   DNS: {alb['DNSName']}")
        print(f"   State: {alb['State']['Code']}")
        print(f"   Type: {alb['Type']}")
        print(f"   Scheme: {alb['Scheme']}")
        print(f"   VPC: {alb['VpcId']}")
        
        is_active = alb['State']['Code'] == 'active'
        
        if is_active:
            print(f"   ✅ Status: Active")
        else:
            print(f"   ⚠️  Status: {alb['State']['Code']}")
        
        return {
            'success': True,
            'alb_name': alb['LoadBalancerName'],
            'alb_arn': alb['LoadBalancerArn'],
            'dns_name': alb['DNSName'],
            'state': alb['State']['Code'],
            'is_active': is_active
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {'success': False, 'error': str(e)}

def verify_target_group() -> Dict[str, Any]:
    """Verify target group status."""
    client = boto3.client('elbv2', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("Verifying Target Group")
    print("=" * 80)
    
    try:
        response = client.describe_target_groups(
            Names=['multimodal-lib-prod-tg-v2']
        )
        
        if not response['TargetGroups']:
            print("❌ Target group not found!")
            return {'success': False, 'error': 'Target group not found'}
        
        tg = response['TargetGroups'][0]
        
        print(f"\n✅ Target Group Found: {tg['TargetGroupName']}")
        print(f"   ARN: {tg['TargetGroupArn']}")
        print(f"   Protocol: {tg['Protocol']}")
        print(f"   Port: {tg['Port']}")
        print(f"   VPC: {tg['VpcId']}")
        print(f"   Target Type: {tg['TargetType']}")
        
        print(f"\n   Health Check Configuration:")
        print(f"   - Path: {tg.get('HealthCheckPath', 'N/A')}")
        print(f"   - Protocol: {tg.get('HealthCheckProtocol', 'N/A')}")
        print(f"   - Interval: {tg.get('HealthCheckIntervalSeconds', 'N/A')}s")
        print(f"   - Timeout: {tg.get('HealthCheckTimeoutSeconds', 'N/A')}s")
        print(f"   - Healthy Threshold: {tg.get('HealthyThresholdCount', 'N/A')}")
        print(f"   - Unhealthy Threshold: {tg.get('UnhealthyThresholdCount', 'N/A')}")
        
        # Check target health
        health_response = client.describe_target_health(
            TargetGroupArn=tg['TargetGroupArn']
        )
        
        targets = health_response['TargetHealthDescriptions']
        
        print(f"\n   Registered Targets: {len(targets)}")
        
        if targets:
            for target in targets:
                target_id = target['Target']['Id']
                target_port = target['Target']['Port']
                health_state = target['TargetHealth']['State']
                
                print(f"   - {target_id}:{target_port} - {health_state}")
        else:
            print(f"   ⚠️  No targets registered yet")
        
        return {
            'success': True,
            'target_group_name': tg['TargetGroupName'],
            'target_group_arn': tg['TargetGroupArn'],
            'target_count': len(targets)
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {'success': False, 'error': str(e)}

def verify_listener() -> Dict[str, Any]:
    """Verify listener configuration."""
    client = boto3.client('elbv2', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("Verifying HTTP Listener")
    print("=" * 80)
    
    try:
        # Get ALB ARN first
        alb_response = client.describe_load_balancers(
            Names=['multimodal-lib-prod-alb-v2']
        )
        
        if not alb_response['LoadBalancers']:
            print("❌ ALB not found!")
            return {'success': False, 'error': 'ALB not found'}
        
        alb_arn = alb_response['LoadBalancers'][0]['LoadBalancerArn']
        
        # Get listeners
        response = client.describe_listeners(
            LoadBalancerArn=alb_arn
        )
        
        if not response['Listeners']:
            print("❌ No listeners found!")
            return {'success': False, 'error': 'No listeners found'}
        
        listener = response['Listeners'][0]
        
        print(f"\n✅ Listener Found")
        print(f"   ARN: {listener['ListenerArn']}")
        print(f"   Protocol: {listener['Protocol']}")
        print(f"   Port: {listener['Port']}")
        
        if listener['DefaultActions']:
            action = listener['DefaultActions'][0]
            print(f"   Default Action: {action['Type']}")
            if 'TargetGroupArn' in action:
                print(f"   Target Group: {action['TargetGroupArn']}")
        
        return {
            'success': True,
            'listener_arn': listener['ListenerArn'],
            'protocol': listener['Protocol'],
            'port': listener['Port']
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {'success': False, 'error': str(e)}

def test_connectivity() -> Dict[str, Any]:
    """Test ALB connectivity."""
    import socket
    
    print("\n" + "=" * 80)
    print("Testing Connectivity")
    print("=" * 80)
    
    dns_name = "multimodal-lib-prod-alb-v2-1090291461.us-east-1.elb.amazonaws.com"
    
    # Test DNS resolution
    print(f"\n1. DNS Resolution Test")
    print(f"   DNS Name: {dns_name}")
    
    try:
        ip_addresses = socket.gethostbyname_ex(dns_name)[2]
        print(f"   ✅ Resolves to: {', '.join(ip_addresses)}")
        dns_ok = True
    except Exception as e:
        print(f"   ❌ DNS resolution failed: {str(e)}")
        dns_ok = False
    
    # Test HTTP connectivity
    print(f"\n2. HTTP Connectivity Test")
    print(f"   Testing: http://{dns_name}/api/health/simple")
    
    try:
        import urllib.request
        
        req = urllib.request.Request(f"http://{dns_name}/api/health/simple")
        
        try:
            response = urllib.request.urlopen(req, timeout=5)
            status_code = response.getcode()
            print(f"   ✅ HTTP {status_code} - ALB is responding")
            http_ok = True
        except urllib.error.HTTPError as e:
            status_code = e.code
            if status_code == 503:
                print(f"   ✅ HTTP 503 - ALB is working (no targets registered yet)")
                http_ok = True
            else:
                print(f"   ⚠️  HTTP {status_code} - Unexpected status")
                http_ok = False
        
    except Exception as e:
        print(f"   ❌ HTTP test failed: {str(e)}")
        http_ok = False
    
    return {
        'success': dns_ok and http_ok,
        'dns_ok': dns_ok,
        'http_ok': http_ok
    }

def main():
    """Main execution function."""
    print("\n" + "=" * 80)
    print("ALB v2 Infrastructure Verification")
    print("=" * 80)
    print(f"\nTimestamp: {datetime.now().isoformat()}")
    print()
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': {}
    }
    
    # Verify ALB
    alb_result = verify_alb()
    results['checks']['alb'] = alb_result
    
    # Verify Target Group
    tg_result = verify_target_group()
    results['checks']['target_group'] = tg_result
    
    # Verify Listener
    listener_result = verify_listener()
    results['checks']['listener'] = listener_result
    
    # Test Connectivity
    connectivity_result = test_connectivity()
    results['checks']['connectivity'] = connectivity_result
    
    # Summary
    print("\n" + "=" * 80)
    print("Verification Summary")
    print("=" * 80)
    
    all_success = all([
        alb_result.get('success', False),
        tg_result.get('success', False),
        listener_result.get('success', False),
        connectivity_result.get('success', False)
    ])
    
    print(f"\n✅ ALB: {'Pass' if alb_result.get('success') else 'Fail'}")
    print(f"✅ Target Group: {'Pass' if tg_result.get('success') else 'Fail'}")
    print(f"✅ Listener: {'Pass' if listener_result.get('success') else 'Fail'}")
    print(f"✅ Connectivity: {'Pass' if connectivity_result.get('success') else 'Fail'}")
    
    results['overall_success'] = all_success
    
    # Save results
    timestamp = int(datetime.now().timestamp())
    output_file = f'alb-v2-verification-{timestamp}.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
    
    if all_success:
        print("\n" + "=" * 80)
        print("✅ ALL CHECKS PASSED - ALB v2 Infrastructure Ready")
        print("=" * 80)
        print("\nNext Step: Update ECS service to use new target group")
        print()
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("❌ SOME CHECKS FAILED - Review errors above")
        print("=" * 80)
        print()
        sys.exit(1)

if __name__ == '__main__':
    main()
