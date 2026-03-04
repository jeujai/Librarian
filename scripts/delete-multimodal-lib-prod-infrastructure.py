#!/usr/bin/env python3
"""
Delete multimodal-lib-prod-alb and its associated VPC infrastructure.
This will clean up the existing infrastructure before recreating with Terraform.
"""

import boto3
import json
import time
from datetime import datetime

def delete_multimodal_lib_infrastructure():
    """Delete multimodal-lib-prod-alb and associated VPC resources."""
    ec2 = boto3.client('ec2')
    elbv2 = boto3.client('elbv2')
    
    print("🗑️ Deleting Multimodal Librarian Infrastructure")
    print("=" * 60)
    
    alb_name = 'multimodal-lib-prod-alb'
    vpc_name = 'multimodal-lib-prod-vpc'
    
    results = {
        'deletion_time': datetime.now().isoformat(),
        'deleted_resources': [],
        'errors': [],
        'success': True
    }
    
    try:
        # Step 1: Delete ALB and associated resources
        print(f"🔍 Looking for ALB: {alb_name}")
        
        try:
            alb_response = elbv2.describe_load_balancers(Names=[alb_name])
            if alb_response['LoadBalancers']:
                alb = alb_response['LoadBalancers'][0]
                alb_arn = alb['LoadBalancerArn']
                vpc_id = alb['VpcId']
                
                print(f"📊 Found ALB: {alb_name}")
                print(f"  DNS: {alb['DNSName']}")
                print(f"  VPC: {vpc_id}")
                print(f"  State: {alb['State']['Code']}")
                
                # Get target groups
                tg_response = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
                target_groups = tg_response['TargetGroups']
                
                print(f"\n🎯 Target Groups: {len(target_groups)}")
                
                # Delete ALB
                print(f"\n🗑️ Deleting ALB: {alb_name}")
                elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
                
                # Wait for ALB deletion
                print("⏳ Waiting for ALB deletion...")
                waiter = elbv2.get_waiter('load_balancers_deleted')
                waiter.wait(LoadBalancerArns=[alb_arn], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
                
                print("✅ ALB deleted successfully")
                results['deleted_resources'].append(f"ALB: {alb_name}")
                
                # Clean up target groups
                for tg in target_groups:
                    try:
                        elbv2.delete_target_group(TargetGroupArn=tg['TargetGroupArn'])
                        print(f"✅ Deleted target group: {tg['TargetGroupName']}")
                        results['deleted_resources'].append(f"Target Group: {tg['TargetGroupName']}")
                    except Exception as e:
                        if "not found" in str(e).lower():
                            print(f"ℹ️ Target group already deleted: {tg['TargetGroupName']}")
                        else:
                            print(f"⚠️ Error deleting target group: {e}")
                            results['errors'].append(f"Target group deletion error: {e}")
                
            else:
                print(f"ℹ️ ALB {alb_name} not found")
                vpc_id = None
                
        except Exception as e:
            if "LoadBalancerNotFound" in str(e) or "does not exist" in str(e):
                print(f"ℹ️ ALB {alb_name} not found")
                vpc_id = None
            else:
                print(f"❌ Error finding ALB: {e}")
                results['errors'].append(f"ALB lookup error: {e}")
                vpc_id = None
        
        # Step 2: Find VPC by name if we don't have it from ALB
        if not vpc_id:
            print(f"\n🔍 Looking for VPC: {vpc_name}")
            vpc_response = ec2.describe_vpcs(
                Filters=[
                    {'Name': 'tag:Name', 'Values': [vpc_name]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )
            
            if vpc_response['Vpcs']:
                vpc_id = vpc_response['Vpcs'][0]['VpcId']
                print(f"📊 Found VPC: {vpc_name} ({vpc_id})")
            else:
                print(f"ℹ️ VPC {vpc_name} not found")
        
        # Step 3: Delete VPC and associated resources
        if vpc_id:
            print(f"\n🗑️ Deleting VPC resources for: {vpc_id}")
            
            # Delete NAT Gateways
            nat_response = ec2.describe_nat_gateways(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for nat_gw in nat_response['NatGateways']:
                if nat_gw['State'] not in ['deleted', 'deleting']:
                    print(f"🗑️ Deleting NAT Gateway: {nat_gw['NatGatewayId']}")
                    ec2.delete_nat_gateway(NatGatewayId=nat_gw['NatGatewayId'])
                    results['deleted_resources'].append(f"NAT Gateway: {nat_gw['NatGatewayId']}")
            
            # Wait for NAT Gateways to be deleted
            if nat_response['NatGateways']:
                print("⏳ Waiting for NAT Gateways to be deleted...")
                time.sleep(60)  # NAT Gateways take time to delete
            
            # Delete Internet Gateway
            igw_response = ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )
            
            for igw in igw_response['InternetGateways']:
                print(f"🗑️ Detaching and deleting Internet Gateway: {igw['InternetGatewayId']}")
                ec2.detach_internet_gateway(
                    InternetGatewayId=igw['InternetGatewayId'],
                    VpcId=vpc_id
                )
                ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
                results['deleted_resources'].append(f"Internet Gateway: {igw['InternetGatewayId']}")
            
            # Delete Subnets
            subnet_response = ec2.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for subnet in subnet_response['Subnets']:
                print(f"🗑️ Deleting Subnet: {subnet['SubnetId']}")
                ec2.delete_subnet(SubnetId=subnet['SubnetId'])
                results['deleted_resources'].append(f"Subnet: {subnet['SubnetId']}")
            
            # Delete Route Tables (except main)
            rt_response = ec2.describe_route_tables(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for rt in rt_response['RouteTables']:
                # Skip main route table
                is_main = any(assoc.get('Main', False) for assoc in rt.get('Associations', []))
                if not is_main:
                    print(f"🗑️ Deleting Route Table: {rt['RouteTableId']}")
                    ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
                    results['deleted_resources'].append(f"Route Table: {rt['RouteTableId']}")
            
            # Delete Security Groups (except default)
            sg_response = ec2.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for sg in sg_response['SecurityGroups']:
                if sg['GroupName'] != 'default':
                    print(f"🗑️ Deleting Security Group: {sg['GroupId']} ({sg['GroupName']})")
                    try:
                        ec2.delete_security_group(GroupId=sg['GroupId'])
                        results['deleted_resources'].append(f"Security Group: {sg['GroupId']}")
                    except Exception as e:
                        print(f"⚠️ Error deleting security group {sg['GroupId']}: {e}")
                        results['errors'].append(f"Security group deletion error: {e}")
            
            # Finally, delete VPC
            print(f"🗑️ Deleting VPC: {vpc_id}")
            ec2.delete_vpc(VpcId=vpc_id)
            results['deleted_resources'].append(f"VPC: {vpc_id}")
            
            print("✅ VPC and associated resources deleted successfully")
        
        print(f"\n🎉 SUCCESS: Infrastructure cleanup completed")
        print(f"💰 This will enable dedicated infrastructure creation via Terraform")
        
        return results
        
    except Exception as e:
        print(f"❌ Error during infrastructure deletion: {e}")
        results['success'] = False
        results['errors'].append(f"General error: {e}")
        return results

def main():
    """Main execution function."""
    print("🚀 Multimodal Librarian Infrastructure Cleanup")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    try:
        results = delete_multimodal_lib_infrastructure()
        
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'multimodal-lib-infrastructure-deletion-{timestamp}.json'
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📝 Results saved to: {results_file}")
        
        if results['success']:
            print(f"\n✅ Infrastructure cleanup completed successfully")
            print(f"📋 Deleted {len(results['deleted_resources'])} resources")
            if results['errors']:
                print(f"⚠️ {len(results['errors'])} warnings/errors occurred")
            return 0
        else:
            print(f"\n❌ Infrastructure cleanup failed")
            print(f"❌ {len(results['errors'])} errors occurred")
            return 1
        
    except Exception as e:
        print(f"❌ Fatal error during cleanup: {e}")
        return 1

if __name__ == "__main__":
    exit(main())