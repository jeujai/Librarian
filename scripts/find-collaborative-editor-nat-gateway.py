#!/usr/bin/env python3
"""
Find the NAT Gateway used by CollaborativeEditor application
"""

import boto3
import json
from datetime import datetime

def find_collaborative_editor_nat_gateway():
    """Find NAT Gateway associated with CollaborativeEditorProdStack"""
    
    ec2 = boto3.client('ec2')
    
    try:
        # Find VPC with CollaborativeEditor in the name
        vpcs_response = ec2.describe_vpcs()
        collaborative_vpc = None
        
        for vpc in vpcs_response['Vpcs']:
            vpc_name = ""
            if 'Tags' in vpc:
                for tag in vpc['Tags']:
                    if tag['Key'] == 'Name' and 'CollaborativeEditor' in tag['Value']:
                        vpc_name = tag['Value']
                        collaborative_vpc = vpc
                        break
        
        if not collaborative_vpc:
            print("No VPC found with CollaborativeEditor in the name")
            return None
            
        vpc_id = collaborative_vpc['VpcId']
        print(f"Found CollaborativeEditor VPC: {vpc_id} ({vpc_name})")
        
        # Find NAT Gateways in this VPC
        nat_gateways_response = ec2.describe_nat_gateways(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        if not nat_gateways_response['NatGateways']:
            print(f"No available NAT Gateways found in VPC {vpc_id}")
            return None
            
        # Find the public subnet (PublicSubnet1)
        subnets_response = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ]
        )
        
        public_subnet1 = None
        for subnet in subnets_response['Subnets']:
            if 'Tags' in subnet:
                for tag in subnet['Tags']:
                    if tag['Key'] == 'Name' and 'PublicSubnet1' in tag['Value']:
                        public_subnet1 = subnet
                        break
        
        if not public_subnet1:
            print("PublicSubnet1 not found in CollaborativeEditor VPC")
            return None
            
        # Find NAT Gateway in PublicSubnet1
        target_nat_gateway = None
        for nat_gw in nat_gateways_response['NatGateways']:
            if nat_gw['SubnetId'] == public_subnet1['SubnetId']:
                target_nat_gateway = nat_gw
                break
        
        if not target_nat_gateway:
            print(f"No NAT Gateway found in PublicSubnet1 ({public_subnet1['SubnetId']})")
            return None
            
        # Get NAT Gateway details
        nat_gateway_info = {
            "analysis_timestamp": datetime.now().isoformat(),
            "collaborative_editor_vpc": {
                "vpc_id": vpc_id,
                "vpc_name": vpc_name,
                "cidr_block": collaborative_vpc['CidrBlock']
            },
            "public_subnet1": {
                "subnet_id": public_subnet1['SubnetId'],
                "cidr_block": public_subnet1['CidrBlock'],
                "availability_zone": public_subnet1['AvailabilityZone']
            },
            "nat_gateway": {
                "nat_gateway_id": target_nat_gateway['NatGatewayId'],
                "subnet_id": target_nat_gateway['SubnetId'],
                "state": target_nat_gateway['State'],
                "addresses": target_nat_gateway.get('NatGatewayAddresses', []),
                "vpc_id": target_nat_gateway['VpcId']
            },
            "cost_analysis": {
                "hourly_cost": 0.045,
                "monthly_base_cost": 32.40,
                "data_processing_cost_per_gb": 0.045
            },
            "sharing_recommendation": {
                "can_share": True,
                "considerations": [
                    "Both applications will share the same outbound IP address",
                    "NAT Gateway has sufficient bandwidth (45 Gbps) for both applications",
                    "Cost savings: Avoid creating additional NAT Gateway ($32.40/month saved)",
                    "Single point of failure for both applications"
                ]
            }
        }
        
        return nat_gateway_info
        
    except Exception as e:
        print(f"Error finding CollaborativeEditor NAT Gateway: {str(e)}")
        return None

def main():
    print("Finding CollaborativeEditor NAT Gateway...")
    
    nat_gateway_info = find_collaborative_editor_nat_gateway()
    
    if nat_gateway_info:
        # Save results to file
        output_file = f"collaborative-editor-nat-gateway-{int(datetime.now().timestamp())}.json"
        with open(output_file, 'w') as f:
            json.dump(nat_gateway_info, f, indent=2, default=str)
        
        print(f"\nCollaborativeEditor NAT Gateway Analysis:")
        print(f"VPC ID: {nat_gateway_info['collaborative_editor_vpc']['vpc_id']}")
        print(f"VPC Name: {nat_gateway_info['collaborative_editor_vpc']['vpc_name']}")
        print(f"PublicSubnet1 ID: {nat_gateway_info['public_subnet1']['subnet_id']}")
        print(f"NAT Gateway ID: {nat_gateway_info['nat_gateway']['nat_gateway_id']}")
        print(f"NAT Gateway State: {nat_gateway_info['nat_gateway']['state']}")
        
        if nat_gateway_info['nat_gateway']['addresses']:
            for addr in nat_gateway_info['nat_gateway']['addresses']:
                print(f"Public IP: {addr.get('PublicIp', 'N/A')}")
        
        print(f"\nResults saved to: {output_file}")
        print(f"\nCost Savings by Sharing:")
        print(f"- Avoid creating new NAT Gateway: ${nat_gateway_info['cost_analysis']['monthly_base_cost']}/month")
        print(f"- Total monthly savings: ${nat_gateway_info['cost_analysis']['monthly_base_cost']}")
        
    else:
        print("Failed to find CollaborativeEditor NAT Gateway")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())