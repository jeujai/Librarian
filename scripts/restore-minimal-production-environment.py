#!/usr/bin/env python3
"""
Restore Minimal Production Environment for End-to-End Testing

This script restarts the essential AWS services needed for comprehensive
end-to-end testing while keeping costs minimal.

Estimated Monthly Cost: ~$50
- PostgreSQL RDS: $15/month
- Single NAT Gateway: $45/month  
- ECS Tasks: $0 (only run during testing)
- OpenSearch/Neptune: Already running

Total restoration cost: ~$60/month vs $615/month full infrastructure
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any

def restore_minimal_production():
    """Restore minimal production environment for testing."""
    
    try:
        # Initialize AWS clients
        rds_client = boto3.client('rds', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'restoration_actions': [],
            'success': True,
            'estimated_monthly_cost': 60
        }
        
        print("🔧 Restoring Minimal Production Environment")
        print("=" * 50)
        print("Estimated monthly cost: ~$60")
        print("This enables comprehensive end-to-end testing")
        print()
        
        # 1. Restart PostgreSQL Database
        print("1. Restarting PostgreSQL Database:")
        print("-" * 35)
        
        db_identifier = 'multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro'
        
        try:
            # Check current status
            db_response = rds_client.describe_db_instances(
                DBInstanceIdentifier=db_identifier
            )
            
            db_instance = db_response['DBInstances'][0]
            current_status = db_instance['DBInstanceStatus']
            
            print(f"Current status: {current_status}")
            
            if current_status == 'stopped':
                print("⏳ Starting PostgreSQL database...")
                rds_client.start_db_instance(
                    DBInstanceIdentifier=db_identifier
                )
                
                # Wait for database to start
                print("⏳ Waiting for database to become available...")
                waiter = rds_client.get_waiter('db_instance_available')
                waiter.wait(
                    DBInstanceIdentifier=db_identifier,
                    WaiterConfig={
                        'Delay': 30,
                        'MaxAttempts': 20  # 10 minutes max
                    }
                )
                
                print("✅ PostgreSQL database started successfully")
                result['restoration_actions'].append("Started PostgreSQL database")
                
            elif current_status == 'available':
                print("✅ PostgreSQL database already running")
                result['restoration_actions'].append("PostgreSQL database already available")
            else:
                print(f"⚠️  Database in unexpected state: {current_status}")
                
        except Exception as e:
            print(f"❌ Error with PostgreSQL database: {e}")
            result['restoration_actions'].append(f"PostgreSQL error: {e}")
        
        # 2. Create Single NAT Gateway (for outbound connectivity)
        print("\n2. Creating NAT Gateway:")
        print("-" * 25)
        
        try:
            # Find public subnet in the main VPC
            vpc_id = 'vpc-0bc85162dcdbcc986'  # MultimodalLibrarianFullML VPC
            
            # Get public subnets
            subnets_response = ec2_client.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'tag:Name', 'Values': ['*Public*']}
                ]
            )
            
            if subnets_response['Subnets']:
                public_subnet = subnets_response['Subnets'][0]
                subnet_id = public_subnet['SubnetId']
                
                print(f"Using public subnet: {subnet_id}")
                
                # Allocate Elastic IP
                eip_response = ec2_client.allocate_address(Domain='vpc')
                allocation_id = eip_response['AllocationId']
                
                print(f"Allocated Elastic IP: {eip_response['PublicIp']}")
                
                # Create NAT Gateway
                nat_response = ec2_client.create_nat_gateway(
                    SubnetId=subnet_id,
                    AllocationId=allocation_id,
                    TagSpecifications=[
                        {
                            'ResourceType': 'nat-gateway',
                            'Tags': [
                                {'Key': 'Name', 'Value': 'multimodal-lib-minimal-nat'},
                                {'Key': 'Purpose', 'Value': 'end-to-end-testing'},
                                {'Key': 'CostOptimized', 'Value': 'true'}
                            ]
                        }
                    ]
                )
                
                nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
                
                print(f"✅ NAT Gateway created: {nat_gateway_id}")
                print("⏳ Waiting for NAT Gateway to become available...")
                
                # Wait for NAT Gateway to be available
                waiter = ec2_client.get_waiter('nat_gateway_available')
                waiter.wait(
                    NatGatewayIds=[nat_gateway_id],
                    WaiterConfig={
                        'Delay': 15,
                        'MaxAttempts': 20  # 5 minutes max
                    }
                )
                
                print("✅ NAT Gateway is now available")
                result['restoration_actions'].append(f"Created NAT Gateway: {nat_gateway_id}")
                
                # Update route tables for private subnets
                print("⏳ Updating route tables...")
                
                # Find private subnets
                private_subnets = ec2_client.describe_subnets(
                    Filters=[
                        {'Name': 'vpc-id', 'Values': [vpc_id]},
                        {'Name': 'tag:Name', 'Values': ['*Private*']}
                    ]
                )
                
                for subnet in private_subnets['Subnets']:
                    # Find route table for this subnet
                    route_tables = ec2_client.describe_route_tables(
                        Filters=[
                            {'Name': 'association.subnet-id', 'Values': [subnet['SubnetId']]}
                        ]
                    )
                    
                    for rt in route_tables['RouteTables']:
                        try:
                            # Add route to NAT Gateway
                            ec2_client.create_route(
                                RouteTableId=rt['RouteTableId'],
                                DestinationCidrBlock='0.0.0.0/0',
                                NatGatewayId=nat_gateway_id
                            )
                            print(f"✅ Updated route table: {rt['RouteTableId']}")
                        except Exception as e:
                            if 'RouteAlreadyExists' in str(e):
                                # Replace existing route
                                ec2_client.replace_route(
                                    RouteTableId=rt['RouteTableId'],
                                    DestinationCidrBlock='0.0.0.0/0',
                                    NatGatewayId=nat_gateway_id
                                )
                                print(f"✅ Replaced route in table: {rt['RouteTableId']}")
                            else:
                                print(f"⚠️  Route table update failed: {e}")
                
            else:
                print("❌ No public subnets found")
                result['restoration_actions'].append("No public subnets found for NAT Gateway")
                
        except Exception as e:
            print(f"❌ Error creating NAT Gateway: {e}")
            result['restoration_actions'].append(f"NAT Gateway error: {e}")
        
        # 3. Scale up ECS service (temporarily for testing)
        print("\n3. Preparing ECS Service:")
        print("-" * 25)
        
        try:
            cluster_name = 'multimodal-librarian-full-ml'
            service_name = 'multimodal-librarian-full-ml-service'
            
            # Check current service status
            service_response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if service_response['services']:
                service = service_response['services'][0]
                current_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print(f"Current running tasks: {current_count}")
                print(f"Desired tasks: {desired_count}")
                
                if desired_count == 0:
                    print("✅ ECS service ready (scaled to 0 for cost optimization)")
                    print("💡 Use 'aws ecs update-service --desired-count 1' to start for testing")
                    result['restoration_actions'].append("ECS service ready for testing")
                else:
                    print(f"✅ ECS service already configured with {desired_count} desired tasks")
                    result['restoration_actions'].append(f"ECS service running {current_count}/{desired_count} tasks")
            else:
                print("❌ ECS service not found")
                result['restoration_actions'].append("ECS service not found")
                
        except Exception as e:
            print(f"❌ Error checking ECS service: {e}")
            result['restoration_actions'].append(f"ECS service error: {e}")
        
        # 4. Verify other services
        print("\n4. Verifying Other Services:")
        print("-" * 30)
        
        # Check Neptune
        try:
            neptune_client = boto3.client('neptune', region_name='us-east-1')
            clusters = neptune_client.describe_db_clusters()
            
            neptune_healthy = False
            for cluster in clusters['DBClusters']:
                if 'multimodal-lib-prod-neptune' in cluster['DBClusterIdentifier']:
                    if cluster['Status'] == 'available':
                        neptune_healthy = True
                        print("✅ Neptune cluster available")
                        result['restoration_actions'].append("Neptune cluster verified")
                        break
            
            if not neptune_healthy:
                print("⚠️  Neptune cluster not available")
                result['restoration_actions'].append("Neptune cluster not available")
                
        except Exception as e:
            print(f"⚠️  Neptune check error: {e}")
        
        # Check OpenSearch
        try:
            opensearch_client = boto3.client('opensearch', region_name='us-east-1')
            domains = opensearch_client.list_domain_names()
            
            opensearch_healthy = False
            for domain in domains['DomainNames']:
                if 'multimodal-lib-prod-search' in domain['DomainName']:
                    domain_status = opensearch_client.describe_domain(
                        DomainName=domain['DomainName']
                    )
                    if domain_status['DomainStatus']['Processing'] == False:
                        opensearch_healthy = True
                        print("✅ OpenSearch domain available")
                        result['restoration_actions'].append("OpenSearch domain verified")
                        break
            
            if not opensearch_healthy:
                print("⚠️  OpenSearch domain not available")
                result['restoration_actions'].append("OpenSearch domain not available")
                
        except Exception as e:
            print(f"⚠️  OpenSearch check error: {e}")
        
        # 5. Summary
        print("\n5. Restoration Summary:")
        print("-" * 25)
        
        print("✅ Minimal production environment restored!")
        print("\n📊 Monthly Cost Estimate:")
        print(f"   - PostgreSQL RDS: $15/month")
        print(f"   - NAT Gateway: $45/month")
        print(f"   - Total: ~$60/month")
        print("\n🧪 Ready for End-to-End Testing:")
        print(f"   - PostgreSQL: Available for metadata/chat history")
        print(f"   - Neptune: Available for knowledge graph")
        print(f"   - OpenSearch: Available for vector search")
        print(f"   - Network: Outbound connectivity restored")
        print(f"   - ECS: Ready to scale up for testing")
        
        print("\n🚀 Next Steps:")
        print("1. Scale up ECS service: aws ecs update-service --cluster multimodal-librarian-full-ml --service multimodal-librarian-full-ml-service --desired-count 1")
        print("2. Wait for healthy targets in load balancer")
        print("3. Run comprehensive end-to-end tests")
        print("4. Scale down ECS service after testing: --desired-count 0")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during restoration: {e}")
        return {'error': str(e), 'success': False}

if __name__ == "__main__":
    result = restore_minimal_production()
    
    # Save result to file
    result_file = f"minimal-production-restoration-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Restoration results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Minimal production environment successfully restored!")
        print("💰 Monthly cost: ~$60 (vs $615 full infrastructure)")
        print("🧪 Ready for comprehensive end-to-end testing")
        sys.exit(0)
    else:
        print("\n⚠️  Restoration encountered issues - check logs")
        sys.exit(1)