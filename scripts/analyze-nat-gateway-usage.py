#!/usr/bin/env python3
"""
Analyze NAT Gateway Usage for Multimodal Librarian

This script analyzes the multimodal-lib-prod-nat-gateway to determine:
1. Current status and configuration
2. Associated subnets and route tables
3. Whether it can be reused for application deployment
4. Cost implications and recommendations
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("🔍 NAT Gateway Usage Analysis")
    print("=" * 60)
    
    # Target NAT Gateway name
    nat_gateway_name = "multimodal-lib-prod-nat-gateway"
    
    try:
        # Initialize AWS clients
        ec2 = boto3.client('ec2')
        
        # Step 1: Find the NAT Gateway by name
        print(f"🎯 Searching for NAT Gateway: {nat_gateway_name}")
        
        # Get all NAT Gateways and filter by name tag
        nat_gateways_response = ec2.describe_nat_gateways()
        target_nat_gateway = None
        
        for nat_gw in nat_gateways_response['NatGateways']:
            if 'Tags' in nat_gw:
                for tag in nat_gw['Tags']:
                    if tag['Key'] == 'Name' and tag['Value'] == nat_gateway_name:
                        target_nat_gateway = nat_gw
                        break
            if target_nat_gateway:
                break
        
        if not target_nat_gateway:
            print(f"❌ NAT Gateway '{nat_gateway_name}' not found")
            
            # List all NAT Gateways for reference
            print(f"\n📋 Available NAT Gateways:")
            for nat_gw in nat_gateways_response['NatGateways']:
                nat_gw_id = nat_gw['NatGatewayId']
                state = nat_gw['State']
                subnet_id = nat_gw['SubnetId']
                
                # Get name tag if available
                name = "Unnamed"
                if 'Tags' in nat_gw:
                    for tag in nat_gw['Tags']:
                        if tag['Key'] == 'Name':
                            name = tag['Value']
                            break
                
                print(f"   - {name} ({nat_gw_id}) - State: {state} - Subnet: {subnet_id}")
            
            return 1
        
        # Step 2: Analyze the NAT Gateway
        nat_gw_id = target_nat_gateway['NatGatewayId']
        state = target_nat_gateway['State']
        subnet_id = target_nat_gateway['SubnetId']
        vpc_id = target_nat_gateway['VpcId']
        
        print(f"✅ Found NAT Gateway: {nat_gateway_name}")
        print(f"   ID: {nat_gw_id}")
        print(f"   State: {state}")
        print(f"   Subnet: {subnet_id}")
        print(f"   VPC: {vpc_id}")
        
        # Get network addresses
        nat_addresses = []
        if 'NatGatewayAddresses' in target_nat_gateway:
            for addr in target_nat_gateway['NatGatewayAddresses']:
                nat_addresses.append({
                    'allocation_id': addr.get('AllocationId', 'N/A'),
                    'network_interface_id': addr.get('NetworkInterfaceId', 'N/A'),
                    'private_ip': addr.get('PrivateIp', 'N/A'),
                    'public_ip': addr.get('PublicIp', 'N/A')
                })
        
        print(f"   Network Addresses: {len(nat_addresses)}")
        for addr in nat_addresses:
            print(f"      - Public IP: {addr['public_ip']}, Private IP: {addr['private_ip']}")
        
        # Step 3: Analyze the subnet and VPC
        print(f"\n🏗️  Analyzing Subnet and VPC...")
        
        # Get subnet details
        subnet_response = ec2.describe_subnets(SubnetIds=[subnet_id])
        subnet = subnet_response['Subnets'][0]
        
        subnet_name = "Unnamed"
        if 'Tags' in subnet:
            for tag in subnet['Tags']:
                if tag['Key'] == 'Name':
                    subnet_name = tag['Value']
                    break
        
        print(f"   Subnet: {subnet_name} ({subnet_id})")
        print(f"   Availability Zone: {subnet['AvailabilityZone']}")
        print(f"   CIDR Block: {subnet['CidrBlock']}")
        print(f"   Map Public IP: {subnet['MapPublicIpOnLaunch']}")
        
        # Get VPC details
        vpc_response = ec2.describe_vpcs(VpcIds=[vpc_id])
        vpc = vpc_response['Vpcs'][0]
        
        vpc_name = "Unnamed"
        if 'Tags' in vpc:
            for tag in vpc['Tags']:
                if tag['Key'] == 'Name':
                    vpc_name = tag['Value']
                    break
        
        print(f"   VPC: {vpc_name} ({vpc_id})")
        print(f"   VPC CIDR Block: {vpc['CidrBlock']}")
        
        # Step 4: Find route tables that use this NAT Gateway
        print(f"\n🛣️  Analyzing Route Tables...")
        
        route_tables_response = ec2.describe_route_tables(
            Filters=[
                {
                    'Name': 'vpc-id',
                    'Values': [vpc_id]
                }
            ]
        )
        
        nat_gateway_routes = []
        for rt in route_tables_response['RouteTables']:
            rt_id = rt['RouteTableId']
            
            # Get route table name
            rt_name = "Unnamed"
            if 'Tags' in rt:
                for tag in rt['Tags']:
                    if tag['Key'] == 'Name':
                        rt_name = tag['Value']
                        break
            
            # Check if this route table uses our NAT Gateway
            uses_nat_gateway = False
            for route in rt['Routes']:
                if route.get('NatGatewayId') == nat_gw_id:
                    uses_nat_gateway = True
                    nat_gateway_routes.append({
                        'route_table_id': rt_id,
                        'route_table_name': rt_name,
                        'destination': route.get('DestinationCidrBlock', 'N/A'),
                        'associations': rt.get('Associations', [])
                    })
                    break
        
        print(f"   Route tables using this NAT Gateway: {len(nat_gateway_routes)}")
        for route_info in nat_gateway_routes:
            print(f"      - {route_info['route_table_name']} ({route_info['route_table_id']})")
            print(f"        Destination: {route_info['destination']}")
            
            # Show associated subnets
            associated_subnets = []
            for assoc in route_info['associations']:
                if 'SubnetId' in assoc:
                    associated_subnets.append(assoc['SubnetId'])
            
            if associated_subnets:
                print(f"        Associated Subnets: {len(associated_subnets)}")
                for subnet_id in associated_subnets:
                    try:
                        subnet_resp = ec2.describe_subnets(SubnetIds=[subnet_id])
                        subnet_info = subnet_resp['Subnets'][0]
                        subnet_name = "Unnamed"
                        if 'Tags' in subnet_info:
                            for tag in subnet_info['Tags']:
                                if tag['Key'] == 'Name':
                                    subnet_name = tag['Value']
                                    break
                        print(f"          - {subnet_name} ({subnet_id}) - {subnet_info['CidrBlock']}")
                    except Exception as e:
                        print(f"          - {subnet_id} (details unavailable)")
        
        # Step 5: Check for current usage (running instances in associated subnets)
        print(f"\n💻 Checking for Active Resources...")
        
        # Get all subnets associated with route tables that use this NAT Gateway
        associated_subnet_ids = []
        for route_info in nat_gateway_routes:
            for assoc in route_info['associations']:
                if 'SubnetId' in assoc:
                    associated_subnet_ids.append(assoc['SubnetId'])
        
        active_resources = {
            'ec2_instances': [],
            'ecs_tasks': [],
            'rds_instances': [],
            'lambda_functions': []
        }
        
        if associated_subnet_ids:
            # Check for EC2 instances
            try:
                instances_response = ec2.describe_instances(
                    Filters=[
                        {
                            'Name': 'subnet-id',
                            'Values': associated_subnet_ids
                        },
                        {
                            'Name': 'instance-state-name',
                            'Values': ['running', 'pending', 'stopping']
                        }
                    ]
                )
                
                for reservation in instances_response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_name = "Unnamed"
                        if 'Tags' in instance:
                            for tag in instance['Tags']:
                                if tag['Key'] == 'Name':
                                    instance_name = tag['Value']
                                    break
                        
                        active_resources['ec2_instances'].append({
                            'id': instance['InstanceId'],
                            'name': instance_name,
                            'state': instance['State']['Name'],
                            'subnet': instance['SubnetId'],
                            'type': instance['InstanceType']
                        })
            except Exception as e:
                print(f"   Warning: Could not check EC2 instances: {str(e)}")
            
            # Check for ECS tasks (simplified check)
            try:
                ecs = boto3.client('ecs')
                clusters_response = ecs.list_clusters()
                
                for cluster_arn in clusters_response['clusterArns']:
                    tasks_response = ecs.list_tasks(cluster=cluster_arn)
                    if tasks_response['taskArns']:
                        # Get task details
                        task_details = ecs.describe_tasks(
                            cluster=cluster_arn,
                            tasks=tasks_response['taskArns']
                        )
                        
                        for task in task_details['tasks']:
                            if task['lastStatus'] in ['RUNNING', 'PENDING']:
                                # Check if task is in one of our subnets
                                if 'attachments' in task:
                                    for attachment in task['attachments']:
                                        if attachment['type'] == 'ElasticNetworkInterface':
                                            for detail in attachment['details']:
                                                if detail['name'] == 'subnetId' and detail['value'] in associated_subnet_ids:
                                                    active_resources['ecs_tasks'].append({
                                                        'arn': task['taskArn'],
                                                        'status': task['lastStatus'],
                                                        'subnet': detail['value'],
                                                        'cluster': cluster_arn.split('/')[-1]
                                                    })
            except Exception as e:
                print(f"   Warning: Could not check ECS tasks: {str(e)}")
        
        # Display active resources
        total_active = (len(active_resources['ec2_instances']) + 
                       len(active_resources['ecs_tasks']) + 
                       len(active_resources['rds_instances']) + 
                       len(active_resources['lambda_functions']))
        
        print(f"   Active Resources Found: {total_active}")
        
        if active_resources['ec2_instances']:
            print(f"   EC2 Instances ({len(active_resources['ec2_instances'])}):")
            for instance in active_resources['ec2_instances']:
                print(f"      - {instance['name']} ({instance['id']}) - {instance['state']} - {instance['type']}")
        
        if active_resources['ecs_tasks']:
            print(f"   ECS Tasks ({len(active_resources['ecs_tasks'])}):")
            for task in active_resources['ecs_tasks']:
                print(f"      - {task['arn'].split('/')[-1]} - {task['status']} - Cluster: {task['cluster']}")
        
        # Step 6: Cost Analysis
        print(f"\n💰 Cost Analysis...")
        
        # NAT Gateway costs approximately $0.045/hour + $0.045/GB processed
        hourly_cost = 0.045
        monthly_cost = hourly_cost * 24 * 30  # ~$32.40/month
        
        print(f"   NAT Gateway Base Cost: ~${hourly_cost}/hour")
        print(f"   Estimated Monthly Cost: ~${monthly_cost:.2f}/month (base only)")
        print(f"   Additional Cost: $0.045/GB data processed")
        
        # Step 7: Reusability Assessment
        print(f"\n🔄 Reusability Assessment...")
        
        can_reuse = True
        reuse_considerations = []
        
        if state != 'available':
            can_reuse = False
            reuse_considerations.append(f"NAT Gateway is not in 'available' state (current: {state})")
        
        if total_active > 0:
            reuse_considerations.append(f"Currently serving {total_active} active resources")
        
        if len(nat_gateway_routes) == 0:
            reuse_considerations.append("No route tables currently configured to use this NAT Gateway")
        
        # Check if it's in the right VPC for multimodal librarian
        if 'multimodal' not in vpc_name.lower() and 'ml' not in vpc_name.lower():
            reuse_considerations.append(f"May not be in the correct VPC for multimodal librarian (VPC: {vpc_name})")
        
        print(f"   Can Reuse: {'✅ Yes' if can_reuse else '❌ No'}")
        
        if reuse_considerations:
            print(f"   Considerations:")
            for consideration in reuse_considerations:
                print(f"      - {consideration}")
        
        # Step 8: Recommendations
        print(f"\n💡 Recommendations...")
        
        if can_reuse and total_active == 0:
            print(f"   ✅ RECOMMENDED: Reuse this NAT Gateway")
            print(f"      - NAT Gateway is available and not currently in use")
            print(f"      - Will save ~${monthly_cost:.2f}/month vs creating a new one")
            print(f"      - Ensure your application subnets route through this NAT Gateway")
        elif can_reuse and total_active > 0:
            print(f"   ⚠️  CONDITIONAL: Can reuse but currently in use")
            print(f"      - NAT Gateway is serving {total_active} active resources")
            print(f"      - Safe to share if resources are compatible")
            print(f"      - Monitor bandwidth usage to avoid conflicts")
        else:
            print(f"   ❌ NOT RECOMMENDED: Create a new NAT Gateway")
            print(f"      - Current NAT Gateway has issues preventing reuse")
            print(f"      - Cost: Additional ~${monthly_cost:.2f}/month")
        
        # Step 9: Save analysis report
        analysis_report = {
            "analysis_timestamp": datetime.now().isoformat(),
            "nat_gateway": {
                "name": nat_gateway_name,
                "id": nat_gw_id,
                "state": state,
                "subnet_id": subnet_id,
                "vpc_id": vpc_id,
                "vpc_name": vpc_name,
                "addresses": nat_addresses
            },
            "route_tables": nat_gateway_routes,
            "active_resources": active_resources,
            "cost_analysis": {
                "hourly_cost": hourly_cost,
                "monthly_base_cost": monthly_cost,
                "data_processing_cost_per_gb": 0.045
            },
            "reusability": {
                "can_reuse": can_reuse,
                "considerations": reuse_considerations,
                "total_active_resources": total_active
            },
            "recommendation": "reuse" if (can_reuse and total_active == 0) else "conditional" if can_reuse else "create_new"
        }
        
        report_filename = f"nat-gateway-analysis-{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(analysis_report, f, indent=2)
        
        print(f"\n📄 Analysis report saved: {report_filename}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        return 1
    
    print(f"\n✅ NAT Gateway analysis completed!")
    return 0

if __name__ == "__main__":
    exit(main())