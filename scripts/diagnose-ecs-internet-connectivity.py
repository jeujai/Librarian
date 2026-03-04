#!/usr/bin/env python3
"""
Diagnose ECS task internet connectivity issues.
Checks route tables, NAT Gateway configuration, and subnet associations.
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'cluster': 'multimodal-lib-prod-cluster',
        'service': 'multimodal-lib-prod-service-alb'
    }
    
    print("=" * 80)
    print("ECS INTERNET CONNECTIVITY DIAGNOSIS")
    print("=" * 80)
    
    # Get service details
    print("\n1. Getting ECS service configuration...")
    service = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )['services'][0]
    
    # Get network configuration
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    subnets = network_config['subnets']
    security_groups = network_config['securityGroups']
    
    print(f"   Service subnets: {subnets}")
    print(f"   Security groups: {security_groups}")
    
    results['subnets'] = subnets
    results['security_groups'] = security_groups
    
    # Check each subnet
    print("\n2. Analyzing subnet configurations...")
    subnet_details = []
    
    for subnet_id in subnets:
        subnet = ec2.describe_subnets(SubnetIds=[subnet_id])['Subnets'][0]
        vpc_id = subnet['VpcId']
        az = subnet['AvailabilityZone']
        cidr = subnet['CidrBlock']
        
        print(f"\n   Subnet: {subnet_id}")
        print(f"   - VPC: {vpc_id}")
        print(f"   - AZ: {az}")
        print(f"   - CIDR: {cidr}")
        
        # Get route table for this subnet
        route_tables = ec2.describe_route_tables(
            Filters=[
                {'Name': 'association.subnet-id', 'Values': [subnet_id]}
            ]
        )['RouteTables']
        
        if not route_tables:
            # Check for main route table
            route_tables = ec2.describe_route_tables(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'association.main', 'Values': ['true']}
                ]
            )['RouteTables']
            print(f"   - Using main route table")
        
        if route_tables:
            rt = route_tables[0]
            rt_id = rt['RouteTableId']
            print(f"   - Route table: {rt_id}")
            
            # Check routes
            print(f"   - Routes:")
            has_internet_route = False
            nat_gateway_id = None
            
            for route in rt['Routes']:
                dest = route.get('DestinationCidrBlock', route.get('DestinationIpv6CidrBlock', 'N/A'))
                
                if 'GatewayId' in route:
                    target = f"Gateway: {route['GatewayId']}"
                    if route['GatewayId'].startswith('igw-'):
                        print(f"     * {dest} -> {target} (INTERNET GATEWAY - PUBLIC SUBNET)")
                    else:
                        print(f"     * {dest} -> {target}")
                elif 'NatGatewayId' in route:
                    target = f"NAT Gateway: {route['NatGatewayId']}"
                    print(f"     * {dest} -> {target}")
                    if dest == '0.0.0.0/0':
                        has_internet_route = True
                        nat_gateway_id = route['NatGatewayId']
                elif 'NetworkInterfaceId' in route:
                    target = f"ENI: {route['NetworkInterfaceId']}"
                    print(f"     * {dest} -> {target}")
                else:
                    target = "local"
                    print(f"     * {dest} -> {target}")
            
            subnet_info = {
                'subnet_id': subnet_id,
                'vpc_id': vpc_id,
                'az': az,
                'cidr': cidr,
                'route_table_id': rt_id,
                'has_internet_route': has_internet_route,
                'nat_gateway_id': nat_gateway_id
            }
            
            if not has_internet_route:
                print(f"   ⚠️  WARNING: No internet route (0.0.0.0/0 -> NAT Gateway) found!")
                subnet_info['issue'] = 'No internet route'
            
            subnet_details.append(subnet_info)
    
    results['subnet_details'] = subnet_details
    
    # Check NAT Gateway status
    print("\n3. Checking NAT Gateway status...")
    nat_gateways = ec2.describe_nat_gateways(
        Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )['NatGateways']
    
    print(f"   Found {len(nat_gateways)} NAT Gateway(s) in VPC {vpc_id}")
    
    nat_gateway_info = []
    for nat in nat_gateways:
        nat_id = nat['NatGatewayId']
        state = nat['State']
        subnet_id = nat['SubnetId']
        
        # Get public IP
        public_ip = None
        for addr in nat.get('NatGatewayAddresses', []):
            public_ip = addr.get('PublicIp')
            break
        
        print(f"\n   NAT Gateway: {nat_id}")
        print(f"   - State: {state}")
        print(f"   - Subnet: {subnet_id}")
        print(f"   - Public IP: {public_ip}")
        
        nat_gateway_info.append({
            'nat_gateway_id': nat_id,
            'state': state,
            'subnet_id': subnet_id,
            'public_ip': public_ip
        })
    
    results['nat_gateways'] = nat_gateway_info
    
    # Check security groups for outbound rules
    print("\n4. Checking security group outbound rules...")
    for sg_id in security_groups:
        sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        print(f"\n   Security Group: {sg_id} ({sg['GroupName']})")
        print(f"   Outbound rules:")
        
        allows_https = False
        for rule in sg['IpPermissionsEgress']:
            protocol = rule.get('IpProtocol', 'N/A')
            from_port = rule.get('FromPort', 'N/A')
            to_port = rule.get('ToPort', 'N/A')
            
            if protocol == '-1':
                print(f"     * ALL traffic allowed")
                allows_https = True
            elif protocol == 'tcp' and (from_port == 443 or to_port == 443 or from_port == -1):
                print(f"     * TCP port 443 (HTTPS) allowed")
                allows_https = True
            else:
                print(f"     * Protocol: {protocol}, Ports: {from_port}-{to_port}")
        
        if not allows_https:
            print(f"   ⚠️  WARNING: Security group may not allow HTTPS outbound!")
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    
    issues_found = []
    
    for subnet_info in subnet_details:
        if not subnet_info['has_internet_route']:
            issue = f"Subnet {subnet_info['subnet_id']} has no internet route"
            issues_found.append(issue)
            print(f"❌ {issue}")
    
    if not issues_found:
        print("✅ All subnets have internet routes via NAT Gateway")
    else:
        print(f"\n🔧 RECOMMENDED FIX:")
        print(f"   Add route 0.0.0.0/0 -> NAT Gateway to the route tables")
        print(f"   for the private subnets where ECS tasks are running.")
    
    results['issues'] = issues_found
    results['diagnosis_complete'] = True
    
    # Save results
    filename = f"ecs-internet-connectivity-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: {filename}")
    
    return results

if __name__ == '__main__':
    main()
