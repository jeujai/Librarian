#!/usr/bin/env python3
"""
Fix NLB connectivity by updating security group to allow port 8000 from anywhere.

The issue: NLB forwards port 80 -> 8000, but security group only allows 8000 from VPC.
Solution: Allow port 8000 from 0.0.0.0/0 since NLB is internet-facing.
"""

import boto3
import json
from datetime import datetime

def fix_security_group():
    """Update security group to allow port 8000 from anywhere."""
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    sg_id = 'sg-0135b368e20b7bd01'
    
    print("=" * 80)
    print("NLB Security Group Fix")
    print("=" * 80)
    print()
    print("Issue: NLB forwards port 80 -> 8000, but security group blocks external traffic")
    print("Solution: Allow port 8000 from 0.0.0.0/0")
    print()
    
    # Get current rules
    print("1. Current Security Group Rules:")
    sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
    
    print(f"   Security Group: {sg_id} ({sg['GroupName']})")
    print(f"   Inbound Rules:")
    for rule in sg['IpPermissions']:
        from_port = rule.get('FromPort', 'All')
        to_port = rule.get('ToPort', 'All')
        protocol = rule.get('IpProtocol', 'All')
        
        sources = []
        for cidr in rule.get('IpRanges', []):
            sources.append(cidr['CidrIp'])
        
        print(f"     - Port {from_port}-{to_port}, Protocol: {protocol}, Sources: {sources}")
    
    # Remove the restrictive rule (port 8000 from VPC only)
    print("\n2. Removing restrictive rule (port 8000 from 10.0.0.0/16)...")
    try:
        ec2.revoke_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 8000,
                'ToPort': 8000,
                'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
            }]
        )
        print("   ✓ Removed")
    except Exception as e:
        print(f"   Note: {e}")
    
    # Add new rule (port 8000 from anywhere)
    print("\n3. Adding new rule (port 8000 from 0.0.0.0/0)...")
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 8000,
                'ToPort': 8000,
                'IpRanges': [{
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'Allow NLB traffic to application port'
                }]
            }]
        )
        print("   ✓ Added")
    except Exception as e:
        print(f"   Error: {e}")
        return False
    
    # Verify new rules
    print("\n4. Updated Security Group Rules:")
    sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
    
    for rule in sg['IpPermissions']:
        from_port = rule.get('FromPort', 'All')
        to_port = rule.get('ToPort', 'All')
        protocol = rule.get('IpProtocol', 'All')
        
        sources = []
        for cidr in rule.get('IpRanges', []):
            sources.append(cidr['CidrIp'])
        
        print(f"     - Port {from_port}-{to_port}, Protocol: {protocol}, Sources: {sources}")
    
    print("\n" + "=" * 80)
    print("Security group updated successfully!")
    print()
    print("The NLB should now be able to forward traffic to the application.")
    print("Test with:")
    print("  curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com/api/health/simple")
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    success = fix_security_group()
    exit(0 if success else 1)
