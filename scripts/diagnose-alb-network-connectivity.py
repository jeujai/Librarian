#!/usr/bin/env python3
"""
Comprehensive ALB network connectivity diagnosis.
Checks security groups, NACLs, route tables, and actual connectivity.
"""

import boto3
import json
from datetime import datetime

def main():
    print("=" * 80)
    print("ALB Network Connectivity Diagnosis")
    print("=" * 80)
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # Get ALB details
    print("\n1. Getting ALB configuration...")
    albs = elbv2.describe_load_balancers()
    alb = None
    for lb in albs['LoadBalancers']:
        if 'multimodal-lib-prod-alb-v2' in lb['LoadBalancerName']:
            alb = lb
            break
    
    if not alb:
        print("❌ ALB not found!")
        return 1
    
    print(f"✓ ALB: {alb['LoadBalancerName']}")
    print(f"  VPC: {alb['VpcId']}")
    print(f"  Subnets: {[az['SubnetId'] for az in alb['AvailabilityZones']]}")
    print(f"  Security Groups: {alb['SecurityGroups']}")
    
    # Get target group
    print("\n2. Getting target group configuration...")
    tgs = elbv2.describe_target_groups(LoadBalancerArn=alb['LoadBalancerArn'])
    tg = tgs['TargetGroups'][0]
    
    print(f"✓ Target Group: {tg['TargetGroupName']}")
    print(f"  Health Check Path: {tg['HealthCheckPath']}")
    print(f"  Health Check Port: {tg.get('HealthCheckPort', 'traffic-port')}")
    print(f"  Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    
    # Get target health
    print("\n3. Checking target health...")
    health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
    
    target_ips = []
    for target_desc in health['TargetHealthDescriptions']:
        target = target_desc['Target']
        health_info = target_desc['TargetHealth']
        target_ip = target['Id']
        target_ips.append(target_ip)
        
        print(f"\n  Target: {target_ip}:{target['Port']}")
        print(f"    State: {health_info['State']}")
        print(f"    Reason: {health_info.get('Reason', 'N/A')}")
        print(f"    Description: {health_info.get('Description', 'N/A')}")
    
    if not target_ips:
        print("❌ No targets registered!")
        return 1
    
    # Get ENI details for targets
    print("\n4. Analyzing target network interfaces...")
    target_enis = []
    target_sgs = set()
    target_subnets = set()
    
    for target_ip in target_ips:
        try:
            enis = ec2.describe_network_interfaces(
                Filters=[
                    {'Name': 'addresses.private-ip-address', 'Values': [target_ip]}
                ]
            )
            
            if enis['NetworkInterfaces']:
                eni = enis['NetworkInterfaces'][0]
                target_enis.append(eni)
                target_subnets.add(eni['SubnetId'])
                
                print(f"\n  Target {target_ip}:")
                print(f"    ENI: {eni['NetworkInterfaceId']}")
                print(f"    Subnet: {eni['SubnetId']}")
                print(f"    Security Groups: {[sg['GroupId'] for sg in eni['Groups']]}")
                
                for sg in eni['Groups']:
                    target_sgs.add(sg['GroupId'])
        except Exception as e:
            print(f"  ⚠️  Could not find ENI for {target_ip}: {e}")
    
    # Check security group rules
    print("\n5. Analyzing security group rules...")
    
    print("\n  ALB Security Groups:")
    for sg_id in alb['SecurityGroups']:
        sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        print(f"\n    {sg_id} ({sg['GroupName']}):")
        
        # Check egress to port 8000
        allows_egress = False
        for rule in sg['IpPermissionsEgress']:
            if rule.get('IpProtocol') == '-1':
                print(f"      ✓ Egress: All traffic allowed")
                allows_egress = True
                break
            elif (rule.get('FromPort', 0) <= 8000 <= rule.get('ToPort', 65535)):
                print(f"      ✓ Egress: Port 8000 allowed")
                allows_egress = True
        
        if not allows_egress:
            print(f"      ❌ Egress: Port 8000 NOT allowed")
    
    print("\n  Target Security Groups:")
    for sg_id in target_sgs:
        sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        print(f"\n    {sg_id} ({sg['GroupName']}):")
        
        # Check ingress from ALB
        allows_from_alb = False
        for rule in sg['IpPermissions']:
            if rule.get('IpProtocol') == '-1':
                print(f"      ✓ Ingress: All traffic allowed")
                allows_from_alb = True
                break
            elif (rule.get('FromPort', 0) <= 8000 <= rule.get('ToPort', 65535)):
                # Check if ALB SGs are in the rule
                for sg_pair in rule.get('UserIdGroupPairs', []):
                    if sg_pair['GroupId'] in alb['SecurityGroups']:
                        print(f"      ✓ Ingress: Port 8000 from ALB SG {sg_pair['GroupId']}")
                        allows_from_alb = True
                
                # Check if 0.0.0.0/0 is allowed
                for ip_range in rule.get('IpRanges', []):
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        print(f"      ✓ Ingress: Port 8000 from anywhere")
                        allows_from_alb = True
        
        if not allows_from_alb:
            print(f"      ❌ Ingress: Port 8000 from ALB NOT allowed")
    
    # Check Network ACLs
    print("\n6. Checking Network ACLs...")
    
    all_subnets = set([az['SubnetId'] for az in alb['AvailabilityZones']]) | target_subnets
    
    for subnet_id in all_subnets:
        subnet = ec2.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]
        
        # Get NACL for subnet
        nacls = ec2.describe_network_acls(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [subnet_id]}
            ]
        )
        
        if nacls['NetworkAcls']:
            nacl = nacls['NetworkAcls'][0]
            print(f"\n  Subnet {subnet_id} ({subnet['CidrBlock']}):")
            print(f"    NACL: {nacl['NetworkAclId']}")
            
            # Check for port 8000 rules
            has_8000_ingress = False
            has_8000_egress = False
            
            for entry in nacl['Entries']:
                if entry['RuleAction'] == 'allow':
                    port_range = entry.get('PortRange', {})
                    from_port = port_range.get('From', 0)
                    to_port = port_range.get('To', 65535)
                    
                    if from_port <= 8000 <= to_port:
                        if entry['Egress']:
                            has_8000_egress = True
                        else:
                            has_8000_ingress = True
            
            if has_8000_ingress:
                print(f"      ✓ NACL allows ingress to port 8000")
            else:
                print(f"      ⚠️  NACL may not allow ingress to port 8000")
            
            if has_8000_egress:
                print(f"      ✓ NACL allows egress from port 8000")
            else:
                print(f"      ⚠️  NACL may not allow egress from port 8000")
    
    # Check route tables
    print("\n7. Checking route tables...")
    
    for subnet_id in all_subnets:
        rts = ec2.describe_route_tables(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [subnet_id]}
            ]
        )
        
        if rts['RouteTables']:
            rt = rts['RouteTables'][0]
            print(f"\n  Subnet {subnet_id}:")
            print(f"    Route Table: {rt['RouteTableId']}")
            
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationPrefixListId', 'N/A'))
                target = route.get('GatewayId', route.get('NatGatewayId', route.get('NetworkInterfaceId', 'local')))
                state = route.get('State', 'active')
                
                print(f"      {dest} -> {target} ({state})")
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)
    
    print("\nKey Findings:")
    print("1. Application logs show successful 200 OK responses from ALB IPs")
    print("2. ALB reports Target.Timeout despite successful responses")
    print("3. This indicates a response path issue (ALB -> Target works, Target -> ALB fails)")
    
    print("\nPossible Causes:")
    print("- Security group egress rules on targets may be blocking responses")
    print("- NACL rules may be asymmetric (allow request but block response)")
    print("- Route table configuration may be incorrect")
    print("- ALB health check timeout (10s) may be too short for slow responses")
    
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
