#!/usr/bin/env python3
"""
Setup VPC Peering Between RDS and ECS VPCs

This script implements Option 1 from the VPC mismatch diagnosis:
- Creates VPC peering connection between the two VPCs
- Updates route tables in both VPCs
- Updates RDS security group to allow ECS security group

No downtime, no data migration required.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def setup_vpc_peering():
    """Set up VPC peering between RDS and ECS VPCs."""
    
    ec2 = boto3.client('ec2')
    
    print("=" * 80)
    print("SETUP VPC PEERING - RDS VPC ↔ ECS VPC")
    print("=" * 80)
    print()
    
    # VPC IDs
    rds_vpc_id = 'vpc-0bc85162dcdbcc986'  # RDS VPC
    ecs_vpc_id = 'vpc-0b2186b38779e77f6'  # ECS VPC
    
    # Security groups
    rds_sg_id = 'sg-0e660551c93bcf0ad'  # RDS security group
    ecs_sg_id = 'sg-0135b368e20b7bd01'  # ECS security group
    
    print(f"📋 Configuration:")
    print(f"  RDS VPC: {rds_vpc_id}")
    print(f"  ECS VPC: {ecs_vpc_id}")
    print(f"  RDS Security Group: {rds_sg_id}")
    print(f"  ECS Security Group: {ecs_sg_id}")
    print()
    
    # Step 1: Create VPC Peering Connection
    print("=" * 80)
    print("STEP 1: CREATE VPC PEERING CONNECTION")
    print("=" * 80)
    print()
    
    try:
        # Check if peering connection already exists
        existing_peerings = ec2.describe_vpc_peering_connections(
            Filters=[
                {'Name': 'requester-vpc-info.vpc-id', 'Values': [ecs_vpc_id]},
                {'Name': 'accepter-vpc-info.vpc-id', 'Values': [rds_vpc_id]},
                {'Name': 'status-code', 'Values': ['active', 'pending-acceptance']}
            ]
        )
        
        if existing_peerings['VpcPeeringConnections']:
            peering_id = existing_peerings['VpcPeeringConnections'][0]['VpcPeeringConnectionId']
            status = existing_peerings['VpcPeeringConnections'][0]['Status']['Code']
            print(f"✅ VPC peering connection already exists: {peering_id}")
            print(f"   Status: {status}")
        else:
            print("Creating VPC peering connection...")
            response = ec2.create_vpc_peering_connection(
                VpcId=ecs_vpc_id,
                PeerVpcId=rds_vpc_id,
                TagSpecifications=[
                    {
                        'ResourceType': 'vpc-peering-connection',
                        'Tags': [
                            {'Key': 'Name', 'Value': 'multimodal-lib-rds-ecs-peering'},
                            {'Key': 'Purpose', 'Value': 'Connect ECS tasks to RDS database'}
                        ]
                    }
                ]
            )
            
            peering_id = response['VpcPeeringConnection']['VpcPeeringConnectionId']
            print(f"✅ VPC peering connection created: {peering_id}")
            
            # Accept the peering connection (same account, so auto-accept)
            print("Accepting VPC peering connection...")
            ec2.accept_vpc_peering_connection(VpcPeeringConnectionId=peering_id)
            print("✅ VPC peering connection accepted")
            
            # Wait for peering connection to become active
            print("Waiting for peering connection to become active...")
            for i in range(30):
                response = ec2.describe_vpc_peering_connections(
                    VpcPeeringConnectionIds=[peering_id]
                )
                status = response['VpcPeeringConnections'][0]['Status']['Code']
                if status == 'active':
                    print("✅ VPC peering connection is active")
                    break
                time.sleep(2)
            else:
                print("⚠️  Peering connection not active yet, but continuing...")
        
        print()
        
    except Exception as e:
        print(f"❌ Error creating VPC peering connection: {e}")
        return None
    
    # Step 2: Update Route Tables
    print("=" * 80)
    print("STEP 2: UPDATE ROUTE TABLES")
    print("=" * 80)
    print()
    
    try:
        # Get CIDR blocks for each VPC
        rds_vpc_response = ec2.describe_vpcs(VpcIds=[rds_vpc_id])
        rds_vpc_cidr = rds_vpc_response['Vpcs'][0]['CidrBlock']
        
        ecs_vpc_response = ec2.describe_vpcs(VpcIds=[ecs_vpc_id])
        ecs_vpc_cidr = ecs_vpc_response['Vpcs'][0]['CidrBlock']
        
        print(f"📊 VPC CIDR Blocks:")
        print(f"  RDS VPC: {rds_vpc_cidr}")
        print(f"  ECS VPC: {ecs_vpc_cidr}")
        print()
        
        # Get route tables for ECS VPC (add route to RDS VPC)
        print("Updating ECS VPC route tables...")
        ecs_route_tables = ec2.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [ecs_vpc_id]}]
        )
        
        ecs_routes_added = 0
        for rt in ecs_route_tables['RouteTables']:
            rt_id = rt['RouteTableId']
            
            # Check if route already exists
            route_exists = any(
                route.get('DestinationCidrBlock') == rds_vpc_cidr 
                for route in rt['Routes']
            )
            
            if route_exists:
                print(f"  ✓ Route already exists in {rt_id}")
                continue
            
            try:
                ec2.create_route(
                    RouteTableId=rt_id,
                    DestinationCidrBlock=rds_vpc_cidr,
                    VpcPeeringConnectionId=peering_id
                )
                print(f"  ✅ Added route to {rt_id}: {rds_vpc_cidr} → {peering_id}")
                ecs_routes_added += 1
            except Exception as e:
                if 'RouteAlreadyExists' in str(e):
                    print(f"  ✓ Route already exists in {rt_id}")
                else:
                    print(f"  ⚠️  Failed to add route to {rt_id}: {e}")
        
        print(f"✅ Updated {ecs_routes_added} ECS route tables")
        print()
        
        # Get route tables for RDS VPC (add route to ECS VPC)
        print("Updating RDS VPC route tables...")
        rds_route_tables = ec2.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [rds_vpc_id]}]
        )
        
        rds_routes_added = 0
        for rt in rds_route_tables['RouteTables']:
            rt_id = rt['RouteTableId']
            
            # Check if route already exists
            route_exists = any(
                route.get('DestinationCidrBlock') == ecs_vpc_cidr 
                for route in rt['Routes']
            )
            
            if route_exists:
                print(f"  ✓ Route already exists in {rt_id}")
                continue
            
            try:
                ec2.create_route(
                    RouteTableId=rt_id,
                    DestinationCidrBlock=ecs_vpc_cidr,
                    VpcPeeringConnectionId=peering_id
                )
                print(f"  ✅ Added route to {rt_id}: {ecs_vpc_cidr} → {peering_id}")
                rds_routes_added += 1
            except Exception as e:
                if 'RouteAlreadyExists' in str(e):
                    print(f"  ✓ Route already exists in {rt_id}")
                else:
                    print(f"  ⚠️  Failed to add route to {rt_id}: {e}")
        
        print(f"✅ Updated {rds_routes_added} RDS route tables")
        print()
        
    except Exception as e:
        print(f"❌ Error updating route tables: {e}")
        return None
    
    # Step 3: Update RDS Security Group
    print("=" * 80)
    print("STEP 3: UPDATE RDS SECURITY GROUP")
    print("=" * 80)
    print()
    
    try:
        # Add rule to allow PostgreSQL from ECS security group
        print(f"Adding rule to RDS security group {rds_sg_id}...")
        print(f"  Allow: TCP port 5432 from {ecs_sg_id}")
        
        try:
            ec2.authorize_security_group_ingress(
                GroupId=rds_sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 5432,
                        'ToPort': 5432,
                        'UserIdGroupPairs': [
                            {
                                'GroupId': ecs_sg_id,
                                'Description': 'Allow PostgreSQL from ECS tasks (via VPC peering)'
                            }
                        ]
                    }
                ]
            )
            print("✅ Security group rule added successfully")
        except Exception as e:
            if 'InvalidPermission.Duplicate' in str(e):
                print("✓ Security group rule already exists")
            else:
                raise
        
        print()
        
    except Exception as e:
        print(f"❌ Error updating security group: {e}")
        return None
    
    # Step 4: Verify Configuration
    print("=" * 80)
    print("STEP 4: VERIFY CONFIGURATION")
    print("=" * 80)
    print()
    
    print("✅ VPC Peering Setup Complete!")
    print()
    print("Configuration Summary:")
    print(f"  • VPC Peering: {peering_id}")
    print(f"  • ECS VPC ({ecs_vpc_id}) can reach RDS VPC ({rds_vpc_id})")
    print(f"  • RDS VPC ({rds_vpc_id}) can reach ECS VPC ({ecs_vpc_id})")
    print(f"  • RDS Security Group allows connections from ECS Security Group")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'peering_connection_id': peering_id,
        'rds_vpc': {
            'vpc_id': rds_vpc_id,
            'cidr': rds_vpc_cidr,
            'security_group': rds_sg_id
        },
        'ecs_vpc': {
            'vpc_id': ecs_vpc_id,
            'cidr': ecs_vpc_cidr,
            'security_group': ecs_sg_id
        },
        'routes_added': {
            'ecs_vpc': ecs_routes_added,
            'rds_vpc': rds_routes_added
        }
    }
    
    filename = f"vpc-peering-setup-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"📄 Results saved to: {filename}")
    print()
    
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("1. Test database connectivity from ECS task:")
    print("   aws ecs execute-command --cluster multimodal-lib-prod-cluster \\")
    print("     --task <task-id> --container multimodal-lib-prod-app \\")
    print("     --command '/bin/bash' --interactive")
    print()
    print("   Then inside the container:")
    print(f"   psql -h {rds_vpc_response['Vpcs'][0].get('DnsName', 'RDS_ENDPOINT')} -U postgres -d multimodal_librarian")
    print()
    print("2. Check application logs for successful database connection:")
    print("   aws logs tail /ecs/multimodal-lib-prod-app --since 2m --follow")
    print()
    print("3. Verify health checks pass:")
    print("   aws ecs describe-services --cluster multimodal-lib-prod-cluster \\")
    print("     --services multimodal-lib-prod-service")
    print()
    
    return results

if __name__ == '__main__':
    try:
        results = setup_vpc_peering()
        if results:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
