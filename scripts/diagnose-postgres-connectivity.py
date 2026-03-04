#!/usr/bin/env python3
"""
Diagnose Postgres connectivity from ECS tasks.
"""

import boto3
import json
from datetime import datetime

def main():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    rds = boto3.client('rds', region_name='us-east-1')
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("POSTGRES CONNECTIVITY DIAGNOSIS")
    print("=" * 80)
    
    # Get database info
    db_host = "multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com"
    
    print(f"\n1. Getting RDS instance details...")
    print(f"   Database host: {db_host}")
    
    # Get RDS instance
    db_instances = rds.describe_db_instances()['DBInstances']
    db_instance = None
    
    for db in db_instances:
        if db['Endpoint']['Address'] == db_host:
            db_instance = db
            break
    
    if not db_instance:
        print(f"   ❌ Database instance not found!")
        return
    
    db_vpc_id = db_instance['DBSubnetGroup']['VpcId']
    db_security_groups = [sg['VpcSecurityGroupId'] for sg in db_instance['VpcSecurityGroups']]
    db_subnets = [subnet['SubnetIdentifier'] for subnet in db_instance['DBSubnetGroup']['Subnets']]
    
    print(f"   Database VPC: {db_vpc_id}")
    print(f"   Database Security Groups: {db_security_groups}")
    print(f"   Database Subnets: {db_subnets}")
    
    # Get ECS task info
    print(f"\n2. Getting ECS task details...")
    
    service = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )['services'][0]
    
    ecs_vpc_id = None
    ecs_security_groups = service['networkConfiguration']['awsvpcConfiguration']['securityGroups']
    ecs_subnets = service['networkConfiguration']['awsvpcConfiguration']['subnets']
    
    # Get VPC from subnet
    subnet = ec2.describe_subnets(SubnetIds=[ecs_subnets[0]])['Subnets'][0]
    ecs_vpc_id = subnet['VpcId']
    
    print(f"   ECS VPC: {ecs_vpc_id}")
    print(f"   ECS Security Groups: {ecs_security_groups}")
    print(f"   ECS Subnets: {ecs_subnets}")
    
    # Check VPC match
    print(f"\n3. Checking VPC compatibility...")
    if db_vpc_id == ecs_vpc_id:
        print(f"   ✅ Database and ECS are in the same VPC")
    else:
        print(f"   ❌ VPC MISMATCH!")
        print(f"      Database VPC: {db_vpc_id}")
        print(f"      ECS VPC: {ecs_vpc_id}")
        print(f"   🔧 FIX: Need VPC peering or move resources to same VPC")
        return
    
    # Check security group rules
    print(f"\n4. Checking security group rules...")
    
    for db_sg_id in db_security_groups:
        db_sg = ec2.describe_security_groups(GroupIds=[db_sg_id])['SecurityGroups'][0]
        print(f"\n   Database SG: {db_sg_id} ({db_sg['GroupName']})")
        print(f"   Inbound rules:")
        
        allows_ecs = False
        for rule in db_sg['IpPermissions']:
            protocol = rule.get('IpProtocol', 'N/A')
            from_port = rule.get('FromPort', 'N/A')
            to_port = rule.get('ToPort', 'N/A')
            
            # Check for port 5432
            if (protocol == 'tcp' and from_port == 5432) or protocol == '-1':
                # Check source
                for source_sg in rule.get('UserIdGroupPairs', []):
                    source_sg_id = source_sg['GroupId']
                    print(f"     * Port {from_port}-{to_port} from SG {source_sg_id}")
                    
                    if source_sg_id in ecs_security_groups:
                        allows_ecs = True
                        print(f"       ✅ Allows ECS security group")
                
                for cidr in rule.get('IpRanges', []):
                    cidr_block = cidr['CidrIp']
                    print(f"     * Port {from_port}-{to_port} from CIDR {cidr_block}")
        
        if not allows_ecs:
            print(f"   ❌ Database SG does NOT allow inbound from ECS SG on port 5432")
            print(f"   🔧 FIX: Add inbound rule to database SG:")
            print(f"      aws ec2 authorize-security-group-ingress \\")
            print(f"        --group-id {db_sg_id} \\")
            print(f"        --protocol tcp \\")
            print(f"        --port 5432 \\")
            print(f"        --source-group {ecs_security_groups[0]}")
        else:
            print(f"   ✅ Database SG allows inbound from ECS SG on port 5432")
    
    # Check ECS SG outbound rules
    print(f"\n5. Checking ECS security group outbound rules...")
    for ecs_sg_id in ecs_security_groups:
        ecs_sg = ec2.describe_security_groups(GroupIds=[ecs_sg_id])['SecurityGroups'][0]
        print(f"\n   ECS SG: {ecs_sg_id} ({ecs_sg['GroupName']})")
        print(f"   Outbound rules:")
        
        allows_postgres = False
        for rule in ecs_sg['IpPermissionsEgress']:
            protocol = rule.get('IpProtocol', 'N/A')
            from_port = rule.get('FromPort', 'N/A')
            to_port = rule.get('ToPort', 'N/A')
            
            if protocol == '-1':
                print(f"     * ALL traffic allowed")
                allows_postgres = True
            elif protocol == 'tcp' and (from_port == 5432 or to_port == 5432 or from_port == -1):
                print(f"     * TCP port 5432 allowed")
                allows_postgres = True
        
        if not allows_postgres:
            print(f"   ⚠️  ECS SG may not allow outbound to Postgres")
        else:
            print(f"   ✅ ECS SG allows outbound to Postgres")
    
    # Check route tables
    print(f"\n6. Checking route tables for connectivity...")
    
    # Get ECS subnet route table
    ecs_route_tables = ec2.describe_route_tables(
        Filters=[
            {'Name': 'association.subnet-id', 'Values': [ecs_subnets[0]]}
        ]
    )['RouteTables']
    
    if not ecs_route_tables:
        ecs_route_tables = ec2.describe_route_tables(
            Filters=[
                {'Name': 'vpc-id', 'Values': [ecs_vpc_id]},
                {'Name': 'association.main', 'Values': ['true']}
            ]
        )['RouteTables']
    
    if ecs_route_tables:
        rt = ecs_route_tables[0]
        print(f"   ECS Route Table: {rt['RouteTableId']}")
        
        # Check for local route
        has_local = False
        for route in rt['Routes']:
            dest = route.get('DestinationCidrBlock', 'N/A')
            if route.get('GatewayId') == 'local':
                has_local = True
                print(f"     * {dest} -> local ✅")
        
        if has_local:
            print(f"   ✅ Local VPC routing is configured")
        else:
            print(f"   ❌ No local VPC route found")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\nIf all checks pass, the issue may be:")
    print("1. Database is not running")
    print("2. Database is in a different availability zone with no route")
    print("3. Network ACLs blocking traffic")
    print("4. Database credentials are incorrect")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'db_vpc': db_vpc_id,
        'ecs_vpc': ecs_vpc_id,
        'vpc_match': db_vpc_id == ecs_vpc_id,
        'db_security_groups': db_security_groups,
        'ecs_security_groups': ecs_security_groups
    }
    
    filename = f"postgres-connectivity-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: {filename}")

if __name__ == '__main__':
    main()
