#!/usr/bin/env python3
"""
Comprehensive cleanup of multimodal-lib-prod infrastructure.
Handles all dependencies properly before deleting VPC.
"""

import boto3
import json
import time
from datetime import datetime

def comprehensive_cleanup():
    """Comprehensive cleanup of all multimodal-lib-prod resources."""
    ec2 = boto3.client('ec2')
    elbv2 = boto3.client('elbv2')
    ecs = boto3.client('ecs')
    
    print("🧹 Comprehensive Multimodal Librarian Cleanup")
    print("=" * 60)
    
    vpc_id = 'vpc-0b2186b38779e77f6'  # Known VPC ID
    
    results = {
        'cleanup_time': datetime.now().isoformat(),
        'cleaned_resources': [],
        'errors': [],
        'success': True
    }
    
    try:
        # Step 1: Stop all ECS services in the VPC
        print("🛑 Stopping ECS services...")
        try:
            clusters = ecs.list_clusters()['clusterArns']
            for cluster_arn in clusters:
                cluster_name = cluster_arn.split('/')[-1]
                if 'multimodal' in cluster_name.lower():
                    print(f"🔍 Checking cluster: {cluster_name}")
                    
                    services = ecs.list_services(cluster=cluster_arn)['serviceArns']
                    for service_arn in services:
                        service_name = service_arn.split('/')[-1]
                        print(f"🛑 Stopping service: {service_name}")
                        
                        # Set desired count to 0
                        ecs.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        results['cleaned_resources'].append(f"ECS Service stopped: {service_name}")
                        
                        # Wait for tasks to stop
                        print("⏳ Waiting for tasks to stop...")
                        time.sleep(30)
        except Exception as e:
            print(f"⚠️ Error stopping ECS services: {e}")
            results['errors'].append(f"ECS service stop error: {e}")
        
        # Step 2: Release Elastic IPs associated with NAT Gateways
        print("\n🔌 Releasing Elastic IPs...")
        try:
            addresses = ec2.describe_addresses(
                Filters=[{'Name': 'domain', 'Values': ['vpc']}]
            )['Addresses']
            
            for addr in addresses:
                if addr.get('AssociationId'):
                    # Check if it's associated with a NAT Gateway in our VPC
                    if addr.get('NetworkInterfaceId'):
                        try:
                            eni = ec2.describe_network_interfaces(
                                NetworkInterfaceIds=[addr['NetworkInterfaceId']]
                            )['NetworkInterfaces'][0]
                            
                            if eni.get('VpcId') == vpc_id:
                                print(f"🔌 Releasing EIP: {addr['PublicIp']}")
                                if addr.get('AssociationId'):
                                    ec2.disassociate_address(AssociationId=addr['AssociationId'])
                                ec2.release_address(AllocationId=addr['AllocationId'])
                                results['cleaned_resources'].append(f"EIP released: {addr['PublicIp']}")
                        except Exception as e:
                            print(f"⚠️ Error with EIP {addr['PublicIp']}: {e}")
                            results['errors'].append(f"EIP error: {e}")
        except Exception as e:
            print(f"⚠️ Error releasing EIPs: {e}")
            results['errors'].append(f"EIP release error: {e}")
        
        # Step 3: Delete NAT Gateways
        print("\n🌐 Deleting NAT Gateways...")
        try:
            nat_gateways = ec2.describe_nat_gateways(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['NatGateways']
            
            for nat_gw in nat_gateways:
                if nat_gw['State'] not in ['deleted', 'deleting']:
                    print(f"🗑️ Deleting NAT Gateway: {nat_gw['NatGatewayId']}")
                    ec2.delete_nat_gateway(NatGatewayId=nat_gw['NatGatewayId'])
                    results['cleaned_resources'].append(f"NAT Gateway: {nat_gw['NatGatewayId']}")
            
            # Wait for NAT Gateways to be deleted
            if nat_gateways:
                print("⏳ Waiting for NAT Gateways to be deleted...")
                time.sleep(120)  # NAT Gateways take time to delete
        except Exception as e:
            print(f"⚠️ Error deleting NAT Gateways: {e}")
            results['errors'].append(f"NAT Gateway deletion error: {e}")
        
        # Step 4: Delete remaining Load Balancers
        print("\n⚖️ Cleaning up any remaining Load Balancers...")
        try:
            lbs = elbv2.describe_load_balancers()['LoadBalancers']
            for lb in lbs:
                if lb['VpcId'] == vpc_id:
                    print(f"🗑️ Deleting Load Balancer: {lb['LoadBalancerName']}")
                    elbv2.delete_load_balancer(LoadBalancerArn=lb['LoadBalancerArn'])
                    results['cleaned_resources'].append(f"Load Balancer: {lb['LoadBalancerName']}")
            
            # Wait for load balancers to be deleted
            time.sleep(60)
        except Exception as e:
            print(f"⚠️ Error deleting Load Balancers: {e}")
            results['errors'].append(f"Load Balancer deletion error: {e}")
        
        # Step 5: Delete Network Interfaces
        print("\n🔌 Cleaning up Network Interfaces...")
        try:
            enis = ec2.describe_network_interfaces(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['NetworkInterfaces']
            
            for eni in enis:
                if eni['Status'] == 'available':  # Only delete available ENIs
                    print(f"🗑️ Deleting ENI: {eni['NetworkInterfaceId']}")
                    try:
                        ec2.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
                        results['cleaned_resources'].append(f"ENI: {eni['NetworkInterfaceId']}")
                    except Exception as e:
                        print(f"⚠️ Error deleting ENI {eni['NetworkInterfaceId']}: {e}")
                        results['errors'].append(f"ENI deletion error: {e}")
        except Exception as e:
            print(f"⚠️ Error cleaning up ENIs: {e}")
            results['errors'].append(f"ENI cleanup error: {e}")
        
        # Step 6: Wait and then delete VPC resources
        print("\n⏳ Waiting for resources to be fully cleaned up...")
        time.sleep(60)
        
        # Delete Internet Gateway
        print("\n🌐 Deleting Internet Gateway...")
        try:
            igws = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )['InternetGateways']
            
            for igw in igws:
                print(f"🗑️ Detaching and deleting IGW: {igw['InternetGatewayId']}")
                ec2.detach_internet_gateway(
                    InternetGatewayId=igw['InternetGatewayId'],
                    VpcId=vpc_id
                )
                ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
                results['cleaned_resources'].append(f"Internet Gateway: {igw['InternetGatewayId']}")
        except Exception as e:
            print(f"⚠️ Error deleting Internet Gateway: {e}")
            results['errors'].append(f"Internet Gateway deletion error: {e}")
        
        # Delete Subnets
        print("\n🏠 Deleting Subnets...")
        try:
            subnets = ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['Subnets']
            
            for subnet in subnets:
                print(f"🗑️ Deleting Subnet: {subnet['SubnetId']}")
                ec2.delete_subnet(SubnetId=subnet['SubnetId'])
                results['cleaned_resources'].append(f"Subnet: {subnet['SubnetId']}")
        except Exception as e:
            print(f"⚠️ Error deleting Subnets: {e}")
            results['errors'].append(f"Subnet deletion error: {e}")
        
        # Delete Route Tables (except main)
        print("\n🛣️ Deleting Route Tables...")
        try:
            route_tables = ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['RouteTables']
            
            for rt in route_tables:
                # Skip main route table
                is_main = any(assoc.get('Main', False) for assoc in rt.get('Associations', []))
                if not is_main:
                    print(f"🗑️ Deleting Route Table: {rt['RouteTableId']}")
                    ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
                    results['cleaned_resources'].append(f"Route Table: {rt['RouteTableId']}")
        except Exception as e:
            print(f"⚠️ Error deleting Route Tables: {e}")
            results['errors'].append(f"Route Table deletion error: {e}")
        
        # Delete Security Groups (except default)
        print("\n🔒 Deleting Security Groups...")
        try:
            security_groups = ec2.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )['SecurityGroups']
            
            for sg in security_groups:
                if sg['GroupName'] != 'default':
                    print(f"🗑️ Deleting Security Group: {sg['GroupId']} ({sg['GroupName']})")
                    try:
                        ec2.delete_security_group(GroupId=sg['GroupId'])
                        results['cleaned_resources'].append(f"Security Group: {sg['GroupId']}")
                    except Exception as e:
                        print(f"⚠️ Error deleting SG {sg['GroupId']}: {e}")
                        results['errors'].append(f"Security Group deletion error: {e}")
        except Exception as e:
            print(f"⚠️ Error deleting Security Groups: {e}")
            results['errors'].append(f"Security Group deletion error: {e}")
        
        # Finally, delete VPC
        print(f"\n🗑️ Deleting VPC: {vpc_id}")
        try:
            ec2.delete_vpc(VpcId=vpc_id)
            results['cleaned_resources'].append(f"VPC: {vpc_id}")
            print("✅ VPC deleted successfully")
        except Exception as e:
            print(f"⚠️ Error deleting VPC: {e}")
            results['errors'].append(f"VPC deletion error: {e}")
        
        print(f"\n🎉 Comprehensive cleanup completed!")
        print(f"📋 Cleaned {len(results['cleaned_resources'])} resources")
        if results['errors']:
            print(f"⚠️ {len(results['errors'])} warnings/errors occurred")
        
        return results
        
    except Exception as e:
        print(f"❌ Fatal error during cleanup: {e}")
        results['success'] = False
        results['errors'].append(f"Fatal error: {e}")
        return results

def main():
    """Main execution function."""
    print("🚀 Comprehensive Multimodal Librarian Infrastructure Cleanup")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    try:
        results = comprehensive_cleanup()
        
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'comprehensive-multimodal-cleanup-{timestamp}.json'
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📝 Results saved to: {results_file}")
        
        if results['success'] and len(results['errors']) == 0:
            print(f"\n✅ Comprehensive cleanup completed successfully")
            return 0
        else:
            print(f"\n⚠️ Cleanup completed with warnings")
            return 0
        
    except Exception as e:
        print(f"❌ Fatal error during cleanup: {e}")
        return 1

if __name__ == "__main__":
    exit(main())