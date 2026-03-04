#!/usr/bin/env python3
"""
Test ALB connectivity to application health check endpoints.
Checks if the ALB can reach the health check path on ECS tasks.
"""

import boto3
import json
import sys
from datetime import datetime

def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def test_alb_health_check_connectivity():
    """Test if ALB can reach application health check endpoints"""
    
    print("=" * 80)
    print("ALB Health Check Connectivity Test")
    print("=" * 80)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    results = {
        'timestamp': get_timestamp(),
        'alb_info': {},
        'target_group_info': {},
        'target_health': [],
        'security_group_analysis': {},
        'issues': [],
        'recommendations': []
    }
    
    # 1. Find the ALB
    print("\n1. Finding multimodal-lib-prod ALB...")
    try:
        albs = elbv2.describe_load_balancers()
        target_alb = None
        
        for alb in albs['LoadBalancers']:
            if alb['LoadBalancerName'] in ['multimodal-lib-prod-alb-v2', 'multimodal-lib-prod-alb']:
                target_alb = alb
                if 'v2' in alb['LoadBalancerName']:
                    break
        
        if not target_alb:
            print("❌ ALB not found!")
            results['issues'].append("ALB not found")
            return results
        
        print(f"✓ Found ALB: {target_alb['LoadBalancerName']}")
        print(f"  DNS: {target_alb['DNSName']}")
        print(f"  Security Groups: {', '.join(target_alb['SecurityGroups'])}")
        
        results['alb_info'] = {
            'name': target_alb['LoadBalancerName'],
            'arn': target_alb['LoadBalancerArn'],
            'dns': target_alb['DNSName'],
            'vpc_id': target_alb['VpcId'],
            'security_groups': target_alb['SecurityGroups']
        }
        
    except Exception as e:
        print(f"❌ Error finding ALB: {e}")
        results['issues'].append(f"Error finding ALB: {str(e)}")
        return results
    
    # 2. Get target group and health check configuration
    print("\n2. Checking target group configuration...")
    try:
        target_groups = elbv2.describe_target_groups(
            LoadBalancerArn=target_alb['LoadBalancerArn']
        )
        
        if not target_groups['TargetGroups']:
            print("❌ No target groups found!")
            results['issues'].append("No target groups configured")
            return results
        
        tg = target_groups['TargetGroups'][0]
        print(f"✓ Target Group: {tg['TargetGroupName']}")
        print(f"  Protocol: {tg['Protocol']}:{tg['Port']}")
        print(f"  Health Check:")
        print(f"    Path: {tg['HealthCheckPath']}")
        print(f"    Protocol: {tg['HealthCheckProtocol']}")
        print(f"    Port: {tg.get('HealthCheckPort', 'traffic-port')}")
        print(f"    Interval: {tg['HealthCheckIntervalSeconds']}s")
        print(f"    Timeout: {tg['HealthCheckTimeoutSeconds']}s")
        print(f"    Healthy Threshold: {tg['HealthyThresholdCount']}")
        print(f"    Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
        
        results['target_group_info'] = {
            'name': tg['TargetGroupName'],
            'arn': tg['TargetGroupArn'],
            'protocol': tg['Protocol'],
            'port': tg['Port'],
            'health_check_path': tg['HealthCheckPath'],
            'health_check_protocol': tg['HealthCheckProtocol'],
            'health_check_port': tg.get('HealthCheckPort', 'traffic-port'),
            'health_check_interval': tg['HealthCheckIntervalSeconds'],
            'health_check_timeout': tg['HealthCheckTimeoutSeconds'],
            'healthy_threshold': tg['HealthyThresholdCount'],
            'unhealthy_threshold': tg['UnhealthyThresholdCount']
        }
        
    except Exception as e:
        print(f"❌ Error getting target group: {e}")
        results['issues'].append(f"Error getting target group: {str(e)}")
        return results
    
    # 3. Check target health
    print("\n3. Checking target health...")
    try:
        health = elbv2.describe_target_health(
            TargetGroupArn=tg['TargetGroupArn']
        )
        
        print(f"  Registered targets: {len(health['TargetHealthDescriptions'])}")
        
        for target_desc in health['TargetHealthDescriptions']:
            target = target_desc['Target']
            health_info = target_desc['TargetHealth']
            
            target_id = target.get('Id', 'unknown')
            target_port = target.get('Port', 'unknown')
            state = health_info['State']
            reason = health_info.get('Reason', 'N/A')
            description = health_info.get('Description', 'N/A')
            
            status_icon = "✓" if state == "healthy" else "❌"
            print(f"  {status_icon} Target: {target_id}:{target_port}")
            print(f"      State: {state}")
            if state != "healthy":
                print(f"      Reason: {reason}")
                print(f"      Description: {description}")
            
            target_result = {
                'id': target_id,
                'port': target_port,
                'state': state,
                'reason': reason,
                'description': description
            }
            results['target_health'].append(target_result)
            
            if state != "healthy":
                results['issues'].append(f"Target {target_id}:{target_port} is {state}: {reason}")
        
    except Exception as e:
        print(f"❌ Error checking target health: {e}")
        results['issues'].append(f"Error checking target health: {str(e)}")
    
    # 4. Analyze security groups for ALB -> ECS connectivity
    print("\n4. Analyzing security group rules...")
    try:
        alb_sgs = results['alb_info']['security_groups']
        
        # Get ECS task security groups by checking the targets
        ecs_sgs = set()
        for target_desc in health['TargetHealthDescriptions']:
            target_id = target_desc['Target'].get('Id', '')
            
            # If it's an IP target, find the ENI and its security group
            if target_id.startswith('10.'):
                # Find network interface with this IP
                try:
                    enis = ec2.describe_network_interfaces(
                        Filters=[
                            {'Name': 'addresses.private-ip-address', 'Values': [target_id]}
                        ]
                    )
                    
                    for eni in enis['NetworkInterfaces']:
                        for sg in eni['Groups']:
                            ecs_sgs.add(sg['GroupId'])
                except Exception as e:
                    print(f"      Could not find ENI for {target_id}: {e}")
        
        print(f"\n  ALB Security Groups: {', '.join(alb_sgs)}")
        for sg_id in alb_sgs:
            sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
            print(f"    {sg_id} ({sg['GroupName']}):")
            
            # Check egress rules
            allows_8000 = False
            for rule in sg['IpPermissionsEgress']:
                if rule.get('IpProtocol') == '-1':
                    allows_8000 = True
                    print(f"      ✓ Egress: All traffic allowed")
                    break
                elif rule.get('FromPort') == 8000 or (rule.get('FromPort', 0) <= 8000 <= rule.get('ToPort', 0)):
                    allows_8000 = True
                    print(f"      ✓ Egress: Port 8000 allowed")
                    break
            
            if not allows_8000:
                print(f"      ❌ Egress: Port 8000 NOT explicitly allowed")
                results['issues'].append(f"ALB security group {sg_id} may not allow egress to port 8000")
        
        if ecs_sgs:
            print(f"\n  ECS Task Security Groups: {', '.join(ecs_sgs)}")
            for sg_id in ecs_sgs:
                sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
                print(f"    {sg_id} ({sg['GroupName']}):")
                
                # Check ingress rules
                allows_alb = False
                for rule in sg['IpPermissions']:
                    if rule.get('FromPort') == 8000 or rule.get('IpProtocol') == '-1':
                        # Check if ALB security groups are allowed
                        for sg_pair in rule.get('UserIdGroupPairs', []):
                            if sg_pair['GroupId'] in alb_sgs:
                                allows_alb = True
                                print(f"      ✓ Ingress: Port 8000 from ALB SG {sg_pair['GroupId']}")
                        
                        # Check if all IPs are allowed
                        for ip_range in rule.get('IpRanges', []):
                            if ip_range.get('CidrIp') == '0.0.0.0/0':
                                allows_alb = True
                                print(f"      ✓ Ingress: Port 8000 from anywhere (0.0.0.0/0)")
                
                if not allows_alb:
                    print(f"      ❌ Ingress: Port 8000 from ALB NOT allowed")
                    results['issues'].append(f"ECS security group {sg_id} does not allow port 8000 from ALB")
                    results['recommendations'].append(
                        f"Add inbound rule to ECS security group {sg_id} allowing port 8000 from ALB security groups: {', '.join(alb_sgs)}"
                    )
        else:
            print("\n  ⚠️  Could not determine ECS task security groups")
            results['issues'].append("Could not determine ECS task security groups")
        
        results['security_group_analysis'] = {
            'alb_security_groups': list(alb_sgs),
            'ecs_security_groups': list(ecs_sgs)
        }
        
    except Exception as e:
        print(f"❌ Error analyzing security groups: {e}")
        results['issues'].append(f"Error analyzing security groups: {str(e)}")
    
    # 5. Check for common health check issues
    print("\n5. Checking for common health check issues...")
    
    # Check health check path
    health_check_path = results['target_group_info']['health_check_path']
    if health_check_path not in ['/health', '/health/simple', '/api/health', '/api/health/simple']:
        print(f"  ⚠️  Unusual health check path: {health_check_path}")
        results['recommendations'].append(f"Verify that the application responds to {health_check_path}")
    else:
        print(f"  ✓ Health check path looks standard: {health_check_path}")
    
    # Check health check timeout vs interval
    timeout = results['target_group_info']['health_check_timeout']
    interval = results['target_group_info']['health_check_interval']
    if timeout >= interval:
        print(f"  ❌ Health check timeout ({timeout}s) >= interval ({interval}s)")
        results['issues'].append(f"Health check timeout ({timeout}s) should be less than interval ({interval}s)")
        results['recommendations'].append(f"Reduce health check timeout to less than {interval}s")
    else:
        print(f"  ✓ Health check timeout ({timeout}s) < interval ({interval}s)")
    
    # Check thresholds
    healthy_threshold = results['target_group_info']['healthy_threshold']
    unhealthy_threshold = results['target_group_info']['unhealthy_threshold']
    print(f"  ℹ️  Healthy threshold: {healthy_threshold} consecutive successes")
    print(f"  ℹ️  Unhealthy threshold: {unhealthy_threshold} consecutive failures")
    
    # 6. Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if results['issues']:
        print("\n❌ Issues Found:")
        for i, issue in enumerate(results['issues'], 1):
            print(f"  {i}. {issue}")
    
    if results['recommendations']:
        print("\n💡 Recommendations:")
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"  {i}. {rec}")
    
    if not results['issues']:
        print("\n✓ All health check connectivity checks passed!")
        print("  The ALB should be able to reach the application health check endpoints.")
    else:
        print("\n⚠️  Health check connectivity issues detected.")
        print("  Review the issues and recommendations above.")
    
    # Save results
    output_file = f"alb-health-check-connectivity-test-{get_timestamp()}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    return results

if __name__ == '__main__':
    try:
        results = test_alb_health_check_connectivity()
        
        # Exit with error code if issues found
        if results.get('issues'):
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
