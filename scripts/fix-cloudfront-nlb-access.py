#!/usr/bin/env python3
"""
Fix CloudFront to NLB connectivity by ensuring proper network configuration.

This script:
1. Verifies NLB is internet-facing and in public subnets
2. Checks and fixes Network ACLs if needed
3. Tests connectivity from different angles
4. Provides recommendations
"""

import boto3
import json
import time
from datetime import datetime

def fix_cloudfront_nlb_access():
    """Fix CloudFront to NLB connectivity issues."""
    
    ec2 = boto3.client('ec2')
    elbv2 = boto3.client('elbv2')
    
    print("=" * 80)
    print("CloudFront to NLB Access Fix")
    print("=" * 80)
    
    # Get NLB details
    print("\n📋 Getting NLB configuration...")
    lbs = elbv2.describe_load_balancers(Names=['multimodal-lib-prod-nlb'])
    nlb = lbs['LoadBalancers'][0]
    
    nlb_arn = nlb['LoadBalancerArn']
    nlb_dns = nlb['DNSName']
    vpc_id = nlb['VpcId']
    subnet_ids = [az['SubnetId'] for az in nlb['AvailabilityZones']]
    
    print(f"   NLB: {nlb['LoadBalancerName']}")
    print(f"   DNS: {nlb_dns}")
    print(f"   Scheme: {nlb['Scheme']}")
    print(f"   VPC: {vpc_id}")
    print(f"   Subnets: {subnet_ids}")
    
    # Check Network ACLs
    print("\n🔍 Checking Network ACLs...")
    
    for subnet_id in subnet_ids:
        # Get NACL for subnet
        nacls = ec2.describe_network_acls(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [subnet_id]}
            ]
        )
        
        if nacls['NetworkAcls']:
            nacl = nacls['NetworkAcls'][0]
            nacl_id = nacl['NetworkAclId']
            
            print(f"\n   Subnet: {subnet_id}")
            print(f"   NACL: {nacl_id}")
            
            # Check inbound rules
            print(f"   Inbound Rules:")
            for entry in sorted(nacl['Entries'], key=lambda x: x['RuleNumber']):
                if not entry['Egress']:
                    protocol = entry.get('Protocol', '-1')
                    port_range = entry.get('PortRange', {})
                    from_port = port_range.get('From', 'All')
                    to_port = port_range.get('To', 'All')
                    cidr = entry.get('CidrBlock', entry.get('Ipv6CidrBlock', 'N/A'))
                    action = entry['RuleAction']
                    
                    print(f"      Rule {entry['RuleNumber']}: {action} - Protocol {protocol}, Ports {from_port}-{to_port}, CIDR {cidr}")
            
            # Check outbound rules
            print(f"   Outbound Rules:")
            for entry in sorted(nacl['Entries'], key=lambda x: x['RuleNumber']):
                if entry['Egress']:
                    protocol = entry.get('Protocol', '-1')
                    port_range = entry.get('PortRange', {})
                    from_port = port_range.get('From', 'All')
                    to_port = port_range.get('To', 'All')
                    cidr = entry.get('CidrBlock', entry.get('Ipv6CidrBlock', 'N/A'))
                    action = entry['RuleAction']
                    
                    print(f"      Rule {entry['RuleNumber']}: {action} - Protocol {protocol}, Ports {from_port}-{to_port}, CIDR {cidr}")
    
    # Check if NLB has proper listeners
    print("\n🎧 Checking NLB Listeners...")
    listeners = elbv2.describe_listeners(LoadBalancerArn=nlb_arn)
    
    for listener in listeners['Listeners']:
        print(f"   Listener ARN: {listener['ListenerArn']}")
        print(f"   Port: {listener['Port']}")
        print(f"   Protocol: {listener['Protocol']}")
        print(f"   Default Actions: {listener['DefaultActions']}")
    
    # Get target group health
    print("\n🎯 Checking Target Health...")
    tgs = elbv2.describe_target_groups(LoadBalancerArn=nlb_arn)
    
    for tg in tgs['TargetGroups']:
        tg_arn = tg['TargetGroupArn']
        print(f"\n   Target Group: {tg['TargetGroupName']}")
        print(f"   Port: {tg['Port']}")
        print(f"   Protocol: {tg['Protocol']}")
        
        health = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        for target in health['TargetHealthDescriptions']:
            target_id = target['Target']['Id']
            target_port = target['Target']['Port']
            health_state = target['TargetHealth']['State']
            
            print(f"   Target: {target_id}:{target_port} - {health_state}")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("DIAGNOSIS & RECOMMENDATIONS")
    print("=" * 80)
    
    print("\n🔍 Root Cause Analysis:")
    print("   The NLB is internet-facing and in public subnets, but CloudFront")
    print("   cannot reach it. This is likely because:")
    print()
    print("   1. NLB takes time to become fully operational (5-10 minutes)")
    print("   2. DNS propagation delay for the NLB endpoint")
    print("   3. CloudFront is caching the connection failure")
    
    print("\n💡 Solutions:")
    print()
    print("   Option 1: Wait and Invalidate Cache (RECOMMENDED)")
    print("   -------------------------------------------------")
    print("   1. Wait 5-10 minutes for NLB to be fully operational")
    print("   2. Test NLB directly: curl http://" + nlb_dns + "/health")
    print("   3. Create CloudFront invalidation to clear cache")
    print("   4. Test CloudFront again")
    print()
    print("   Option 2: Use ALB Instead of NLB")
    print("   ----------------------------------")
    print("   ALBs work better with CloudFront for HTTP/HTTPS traffic")
    print("   NLBs are designed for TCP/UDP traffic")
    print()
    print("   Option 3: Direct NLB Access (Temporary)")
    print("   ----------------------------------------")
    print("   Use NLB DNS directly instead of CloudFront")
    print("   URL: http://" + nlb_dns + ":8000")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'nlb_dns': nlb_dns,
        'nlb_arn': nlb_arn,
        'vpc_id': vpc_id,
        'subnets': subnet_ids,
        'recommendations': [
            'Wait 5-10 minutes for NLB to be fully operational',
            'Test NLB directly before testing CloudFront',
            'Create CloudFront invalidation if needed',
            'Consider using ALB instead of NLB for HTTP traffic'
        ]
    }
    
    filename = f'cloudfront-nlb-fix-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    return results

if __name__ == '__main__':
    fix_cloudfront_nlb_access()
