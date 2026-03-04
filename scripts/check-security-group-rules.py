#!/usr/bin/env python3
"""Check security group rules for ALB and ECS tasks"""

import boto3
import json

def check_security_groups():
    ec2 = boto3.client('ec2')
    
    alb_sg = 'sg-0135b368e20b7bd01'
    ecs_sg = 'sg-0393d472e770ed1a3'
    
    print("=" * 80)
    print("SECURITY GROUP RULES ANALYSIS")
    print("=" * 80)
    
    # Check ALB security group
    print(f"\n1. ALB Security Group: {alb_sg}")
    print("-" * 80)
    
    alb_sg_details = ec2.describe_security_groups(GroupIds=[alb_sg])['SecurityGroups'][0]
    
    print(f"\nName: {alb_sg_details['GroupName']}")
    print(f"VPC: {alb_sg_details['VpcId']}")
    
    print("\nINBOUND RULES:")
    for rule in alb_sg_details['IpPermissions']:
        protocol = rule.get('IpProtocol', 'all')
        from_port = rule.get('FromPort', 'all')
        to_port = rule.get('ToPort', 'all')
        
        sources = []
        if rule.get('IpRanges'):
            sources.extend([r['CidrIp'] for r in rule['IpRanges']])
        if rule.get('UserIdGroupPairs'):
            sources.extend([r['GroupId'] for r in rule['UserIdGroupPairs']])
        
        print(f"  Protocol: {protocol}, Ports: {from_port}-{to_port}")
        print(f"  Sources: {', '.join(sources) if sources else 'None'}")
    
    print("\nOUTBOUND RULES:")
    for rule in alb_sg_details['IpPermissionsEgress']:
        protocol = rule.get('IpProtocol', 'all')
        from_port = rule.get('FromPort', 'all')
        to_port = rule.get('ToPort', 'all')
        
        destinations = []
        if rule.get('IpRanges'):
            destinations.extend([r['CidrIp'] for r in rule['IpRanges']])
        if rule.get('UserIdGroupPairs'):
            destinations.extend([r['GroupId'] for r in rule['UserIdGroupPairs']])
        
        print(f"  Protocol: {protocol}, Ports: {from_port}-{to_port}")
        print(f"  Destinations: {', '.join(destinations) if destinations else 'None'}")
    
    # Check ECS security group
    print(f"\n\n2. ECS Task Security Group: {ecs_sg}")
    print("-" * 80)
    
    ecs_sg_details = ec2.describe_security_groups(GroupIds=[ecs_sg])['SecurityGroups'][0]
    
    print(f"\nName: {ecs_sg_details['GroupName']}")
    print(f"VPC: {ecs_sg_details['VpcId']}")
    
    print("\nINBOUND RULES:")
    allows_alb = False
    for rule in ecs_sg_details['IpPermissions']:
        protocol = rule.get('IpProtocol', 'all')
        from_port = rule.get('FromPort', 'all')
        to_port = rule.get('ToPort', 'all')
        
        sources = []
        if rule.get('IpRanges'):
            sources.extend([r['CidrIp'] for r in rule['IpRanges']])
        if rule.get('UserIdGroupPairs'):
            sg_sources = [r['GroupId'] for r in rule['UserIdGroupPairs']]
            sources.extend(sg_sources)
            if alb_sg in sg_sources:
                allows_alb = True
        
        print(f"  Protocol: {protocol}, Ports: {from_port}-{to_port}")
        print(f"  Sources: {', '.join(sources) if sources else 'None'}")
    
    print("\nOUTBOUND RULES:")
    for rule in ecs_sg_details['IpPermissionsEgress']:
        protocol = rule.get('IpProtocol', 'all')
        from_port = rule.get('FromPort', 'all')
        to_port = rule.get('ToPort', 'all')
        
        destinations = []
        if rule.get('IpRanges'):
            destinations.extend([r['CidrIp'] for r in rule['IpRanges']])
        if rule.get('UserIdGroupPairs'):
            destinations.extend([r['GroupId'] for r in rule['UserIdGroupPairs']])
        
        print(f"  Protocol: {protocol}, Ports: {from_port}-{to_port}")
        print(f"  Destinations: {', '.join(destinations) if destinations else 'None'}")
    
    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    
    if allows_alb:
        print(f"\n✅ ECS security group ALLOWS traffic from ALB security group")
    else:
        print(f"\n❌ ECS security group DOES NOT allow traffic from ALB security group!")
        print(f"\n🔧 FIX NEEDED:")
        print(f"   Add inbound rule to {ecs_sg}:")
        print(f"   - Protocol: TCP")
        print(f"   - Port: 8000")
        print(f"   - Source: {alb_sg}")

if __name__ == '__main__':
    check_security_groups()
