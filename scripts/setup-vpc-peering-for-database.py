#!/usr/bin/env python3
"""
Setup VPC peering between ECS VPC and Database VPC.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # VPC IDs
    ecs_vpc_id = 'vpc-0b2186b38779e77f6'  # ECS VPC
    db_vpc_id = 'vpc-0bc85162dcdbcc986'   # Database VPC
    
    print("=" * 80)
    print("VPC PEERING SETUP FOR DATABASE CONNECTIVITY")
    print("=" * 80)
    
    print(f"\nECS VPC: {ecs_vpc_id}")
    print(f"Database VPC: {db_vpc_id}")
    
    # Get VPC CIDR blocks
    print("\n1. Getting VPC CIDR blocks...")
    
    ecs_vpc = ec2.describe_vpcs(VpcIds=[ecs_vpc_id])['Vpcs'][0]
    db_vpc = ec2.describe_vpcs(VpcIds=[db_vpc_id])['Vpcs'][0]
    
    ecs_cidr = ecs_vpc['CidrBlock']
    db_cidr = db_vpc['CidrBlock']
    
    print(f"   ECS VPC CIDR: {ecs_cidr}")
    print(f"   Database VPC CIDR: {db_cidr}")
    
    # Check for existing peering connections
    print("\n2. Checking for existing peering connections...")
    
    existing_peerings = ec2.describe_vpc_peering_connections(
        Filters=[
            {'Name': 'requester-vpc-info.vpc-id', 'Values': [ecs_vpc_id, db_vpc_id]},
            {'Name': 'accepter-vpc-info.vpc-id', 'Values': [ecs_vpc_id, db_vpc_id]},
            {'Name': 'status-code', 'Values': ['active', 'pending-acceptance']}
        ]
    )['VpcPeeringConnections']
    
    if existing_peerings:
        print(f"   Found {len(existing_peerings)} existing peering connection(s)")
        for peering in existing_peerings:
            pcx_id = peering['VpcPeeringConnectionId']
            status = peering['Status']['Code']
            print(f"   - {pcx_id}: {status}")
            
            if status == 'active':
                print(f"\n   ✅ Active peering connection already exists: {pcx_id}")
                peering_id = pcx_id
            else:
                print(f"\n   Peering connection exists but not active")
                peering_id = pcx_id
    else:
        # Create peering connection
        print("\n3. Creating VPC peering connection...")
        
        response = ec2.create_vpc_peering_connection(
            VpcId=ecs_vpc_id,
            PeerVpcId=db_vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'vpc-peering-connection',
                    'Tags': [
                        {'Key': 'Name', 'Value': 'ecs-to-database-peering'},
                        {'Key': 'Purpose', 'Value': 'ECS to RDS connectivity'}
                    ]
                }
            ]
        )
        
        peering_id = response['VpcPeeringConnection']['VpcPeeringConnectionId']
        print(f"   ✅ Peering connection created: {peering_id}")
        
        # Accept peering connection (same account)
        print("\n4. Accepting peering connection...")
        ec2.accept_vpc_peering_connection(
            VpcPeeringConnectionId=peering_id
        )
        
        print(f"   ✅ Peering connection accepted")
        
        # Wait for peering to become active
        print("\n5. Waiting for peering connection to become active...")
        for i in range(30):
            time.sleep(2)
            
            peering = ec2.describe_vpc_peering_connections(
                VpcPeeringConnectionIds=[peering_id]
            )['VpcPeeringConnections'][0]
            
            status = peering['Status']['Code']
            print(f"   Status: {status}")
            
            if status == 'active':
                print(f"   ✅ Peering connection is active!")
                break
        else:
            print(f"   ⚠️  Peering connection not active yet")
    
    # Update route tables
    print("\n6. Updating route tables...")
    
    # Get ECS route tables
    ecs_route_tables = ec2.describe_route_tables(
        Filters=[
            {'Name': 'vpc-id', 'Values': [ecs_vpc_id]}
        ]
    )['RouteTables']
    
    print(f"\n   Updating ECS VPC route tables to route to Database VPC...")
    for rt in ecs_route_tables:
        rt_id = rt['RouteTableId']
        
        # Check if route already exists
        route_exists = False
        for route in rt['Routes']:
            if route.get('DestinationCidrBlock') == db_cidr:
                route_exists = True
                print(f"   - {rt_id}: Route already exists")
                break
        
        if not route_exists:
            try:
                ec2.create_route(
                    RouteTableId=rt_id,
                    DestinationCidrBlock=db_cidr,
                    VpcPeeringConnectionId=peering_id
                )
                print(f"   - {rt_id}: ✅ Route added ({db_cidr} -> {peering_id})")
            except Exception as e:
                if 'RouteAlreadyExists' in str(e):
                    print(f"   - {rt_id}: Route already exists")
                else:
                    print(f"   - {rt_id}: ❌ Error: {e}")
    
    # Get Database route tables
    db_route_tables = ec2.describe_route_tables(
        Filters=[
            {'Name': 'vpc-id', 'Values': [db_vpc_id]}
        ]
    )['RouteTables']
    
    print(f"\n   Updating Database VPC route tables to route to ECS VPC...")
    for rt in db_route_tables:
        rt_id = rt['RouteTableId']
        
        # Check if route already exists
        route_exists = False
        for route in rt['Routes']:
            if route.get('DestinationCidrBlock') == ecs_cidr:
                route_exists = True
                print(f"   - {rt_id}: Route already exists")
                break
        
        if not route_exists:
            try:
                ec2.create_route(
                    RouteTableId=rt_id,
                    DestinationCidrBlock=ecs_cidr,
                    VpcPeeringConnectionId=peering_id
                )
                print(f"   - {rt_id}: ✅ Route added ({ecs_cidr} -> {peering_id})")
            except Exception as e:
                if 'RouteAlreadyExists' in str(e):
                    print(f"   - {rt_id}: Route already exists")
                else:
                    print(f"   - {rt_id}: ❌ Error: {e}")
    
    # Update database security group
    print("\n7. Updating database security group...")
    
    db_sg_id = 'sg-0e660551c93bcf0ad'
    ecs_sg_id = 'sg-0135b368e20b7bd01'
    
    try:
        ec2.authorize_security_group_ingress(
            GroupId=db_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 5432,
                    'ToPort': 5432,
                    'UserIdGroupPairs': [
                        {
                            'GroupId': ecs_sg_id,
                            'Description': 'Allow ECS tasks to connect to Postgres'
                        }
                    ]
                }
            ]
        )
        print(f"   ✅ Added inbound rule to database SG: Port 5432 from {ecs_sg_id}")
    except Exception as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f"   ✅ Security group rule already exists")
        else:
            print(f"   ❌ Error: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("VPC PEERING SETUP COMPLETE")
    print("=" * 80)
    
    print(f"\n✅ VPC Peering Connection: {peering_id}")
    print(f"✅ Routes added to both VPCs")
    print(f"✅ Database security group updated")
    
    print(f"\n📋 Next steps:")
    print(f"   1. Wait 30 seconds for routes to propagate")
    print(f"   2. Check application logs for database connectivity")
    print(f"   3. Verify ALB health checks pass")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'peering_connection_id': peering_id,
        'ecs_vpc': ecs_vpc_id,
        'db_vpc': db_vpc_id,
        'ecs_cidr': ecs_cidr,
        'db_cidr': db_cidr,
        'status': 'complete'
    }
    
    filename = f"vpc-peering-setup-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: {filename}")

if __name__ == '__main__':
    main()
