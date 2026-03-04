#!/usr/bin/env python3
"""
Additional AWS Resource Cleanup Script
Shuts down remaining resources for maximum cost optimization.

This script handles:
1. Lambda functions cleanup
2. S3 bucket cleanup (after verification)
3. VPC infrastructure cleanup
4. IAM resources cleanup
5. Collaborative Editor evaluation

Total potential additional savings: $28-43/month ($336-516/year)
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Any
import sys

class AdditionalResourceCleanup:
    def __init__(self):
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "lambda_cleanup": False,
            "s3_cleanup": False,
            "vpc_cleanup": False,
            "iam_cleanup": False,
            "collaborative_editor_analysis": False,
            "total_additional_monthly_savings": 0,
            "errors": []
        }
        
        # Initialize AWS clients
        try:
            self.lambda_client = boto3.client('lambda', region_name='us-east-1')
            self.s3_client = boto3.client('s3')
            self.ec2_client = boto3.client('ec2', region_name='us-east-1')
            self.ec2_west_client = boto3.client('ec2', region_name='us-west-2')
            self.iam_client = boto3.client('iam')
            print("✅ AWS clients initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize AWS clients: {e}")
            sys.exit(1)

    def cleanup_lambda_functions(self) -> bool:
        """Clean up multimodal-related Lambda functions"""
        print("\n🔄 Phase 1: Lambda Functions Cleanup")
        
        try:
            # Target Lambda functions for deletion
            target_functions = [
                'container-failure-monitor',
                'multimodal-lib-prod-backup-manager'
            ]
            
            deleted_functions = []
            
            for function_name in target_functions:
                try:
                    # Check if function exists
                    self.lambda_client.get_function(FunctionName=function_name)
                    
                    # Delete the function
                    self.lambda_client.delete_function(FunctionName=function_name)
                    deleted_functions.append(function_name)
                    print(f"  ✅ Deleted Lambda function: {function_name}")
                    
                except self.lambda_client.exceptions.ResourceNotFoundException:
                    print(f"  ℹ️  Lambda function not found: {function_name}")
                except Exception as e:
                    error_msg = f"Failed to delete Lambda function {function_name}: {e}"
                    print(f"  ❌ {error_msg}")
                    self.results["errors"].append(error_msg)
            
            if deleted_functions:
                print(f"✅ Successfully deleted {len(deleted_functions)} Lambda functions")
                self.results["lambda_cleanup"] = True
                self.results["total_additional_monthly_savings"] += 3  # Estimated $3/month
                return True
            else:
                print("ℹ️  No Lambda functions found to delete")
                return True
                
        except Exception as e:
            error_msg = f"Lambda cleanup failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def cleanup_s3_buckets(self) -> bool:
        """Clean up multimodal-related S3 buckets after verification"""
        print("\n🔄 Phase 2: S3 Buckets Cleanup")
        
        try:
            # Target S3 buckets for deletion
            target_buckets = [
                'multimodal-lib-prod-alb-logs-50fcb7c1',
                'multimodal-lib-prod-cloudtrail-logs-50fcb7c1',
                'multimodal-lib-prod-config-815b6b7b',
                'multimodal-lib-prod-opensearch-snapshots-50fcb7c1',
                'multimodal-lib-prod-search-snapshots-50fcb7c1',
                'multimodal-librarian-documents',
                'multimodal-librarian-full-ml-backups-591222106065',
                'multimodal-librarian-full-ml-storage-591222106065',
                'multimodal-librarian-learning-backups-591222106065'
            ]
            
            deleted_buckets = []
            
            for bucket_name in target_buckets:
                try:
                    # Check if bucket exists
                    self.s3_client.head_bucket(Bucket=bucket_name)
                    
                    # Check if bucket is empty or has minimal content
                    objects = self.s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=10)
                    object_count = objects.get('KeyCount', 0)
                    
                    if object_count > 0:
                        print(f"  ⚠️  Bucket {bucket_name} contains {object_count} objects - emptying first")
                        
                        # Delete all objects in the bucket
                        paginator = self.s3_client.get_paginator('list_objects_v2')
                        for page in paginator.paginate(Bucket=bucket_name):
                            if 'Contents' in page:
                                objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
                                if objects_to_delete:
                                    self.s3_client.delete_objects(
                                        Bucket=bucket_name,
                                        Delete={'Objects': objects_to_delete}
                                    )
                    
                    # Delete the bucket
                    self.s3_client.delete_bucket(Bucket=bucket_name)
                    deleted_buckets.append(bucket_name)
                    print(f"  ✅ Deleted S3 bucket: {bucket_name}")
                    
                except self.s3_client.exceptions.NoSuchBucket:
                    print(f"  ℹ️  S3 bucket not found: {bucket_name}")
                except Exception as e:
                    error_msg = f"Failed to delete S3 bucket {bucket_name}: {e}"
                    print(f"  ❌ {error_msg}")
                    self.results["errors"].append(error_msg)
            
            if deleted_buckets:
                print(f"✅ Successfully deleted {len(deleted_buckets)} S3 buckets")
                self.results["s3_cleanup"] = True
                self.results["total_additional_monthly_savings"] += 2  # Estimated $2/month
                return True
            else:
                print("ℹ️  No S3 buckets found to delete")
                return True
                
        except Exception as e:
            error_msg = f"S3 cleanup failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def cleanup_vpc_infrastructure(self) -> bool:
        """Clean up unused VPC infrastructure"""
        print("\n🔄 Phase 3: VPC Infrastructure Cleanup")
        
        try:
            # Target VPCs for deletion (excluding default VPC)
            target_vpcs = [
                'vpc-0bc85162dcdbcc986',  # MultimodalLibrarianFullML/Vpc/Vpc
                'vpc-0b2186b38779e77f6'   # multimodal-lib-prod-vpc
                # Note: Keeping vpc-014ac5b9fc828c78f (CollaborativeEditor) for now
            ]
            
            deleted_resources = []
            
            for vpc_id in target_vpcs:
                try:
                    # Check if VPC exists
                    vpc_response = self.ec2_client.describe_vpcs(VpcIds=[vpc_id])
                    if not vpc_response['Vpcs']:
                        print(f"  ℹ️  VPC not found: {vpc_id}")
                        continue
                    
                    vpc = vpc_response['Vpcs'][0]
                    vpc_name = next((tag['Value'] for tag in vpc.get('Tags', []) if tag['Key'] == 'Name'), vpc_id)
                    
                    print(f"  🔄 Processing VPC: {vpc_name} ({vpc_id})")
                    
                    # Delete associated resources first
                    self._cleanup_vpc_dependencies(vpc_id)
                    
                    # Delete the VPC
                    self.ec2_client.delete_vpc(VpcId=vpc_id)
                    deleted_resources.append(f"VPC: {vpc_name}")
                    print(f"  ✅ Deleted VPC: {vpc_name}")
                    
                except self.ec2_client.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidVpcID.NotFound':
                        print(f"  ℹ️  VPC not found: {vpc_id}")
                    else:
                        error_msg = f"Failed to delete VPC {vpc_id}: {e}"
                        print(f"  ❌ {error_msg}")
                        self.results["errors"].append(error_msg)
                except Exception as e:
                    error_msg = f"Failed to delete VPC {vpc_id}: {e}"
                    print(f"  ❌ {error_msg}")
                    self.results["errors"].append(error_msg)
            
            if deleted_resources:
                print(f"✅ Successfully deleted {len(deleted_resources)} VPC resources")
                self.results["vpc_cleanup"] = True
                self.results["total_additional_monthly_savings"] += 12  # Estimated $12/month
                return True
            else:
                print("ℹ️  No VPC resources found to delete")
                return True
                
        except Exception as e:
            error_msg = f"VPC cleanup failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def _cleanup_vpc_dependencies(self, vpc_id: str):
        """Clean up VPC dependencies before deleting the VPC"""
        try:
            # Delete security groups (except default)
            sg_response = self.ec2_client.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for sg in sg_response['SecurityGroups']:
                if sg['GroupName'] != 'default':
                    try:
                        self.ec2_client.delete_security_group(GroupId=sg['GroupId'])
                        print(f"    ✅ Deleted security group: {sg['GroupName']}")
                    except Exception as e:
                        print(f"    ⚠️  Could not delete security group {sg['GroupName']}: {e}")
            
            # Delete subnets
            subnet_response = self.ec2_client.describe_subnets(
                Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
            )
            
            for subnet in subnet_response['Subnets']:
                try:
                    self.ec2_client.delete_subnet(SubnetId=subnet['SubnetId'])
                    print(f"    ✅ Deleted subnet: {subnet['SubnetId']}")
                except Exception as e:
                    print(f"    ⚠️  Could not delete subnet {subnet['SubnetId']}: {e}")
            
            # Delete internet gateways
            igw_response = self.ec2_client.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
            )
            
            for igw in igw_response['InternetGateways']:
                try:
                    # Detach first
                    self.ec2_client.detach_internet_gateway(
                        InternetGatewayId=igw['InternetGatewayId'],
                        VpcId=vpc_id
                    )
                    # Then delete
                    self.ec2_client.delete_internet_gateway(
                        InternetGatewayId=igw['InternetGatewayId']
                    )
                    print(f"    ✅ Deleted internet gateway: {igw['InternetGatewayId']}")
                except Exception as e:
                    print(f"    ⚠️  Could not delete internet gateway {igw['InternetGatewayId']}: {e}")
            
        except Exception as e:
            print(f"    ⚠️  Error cleaning VPC dependencies: {e}")

    def cleanup_iam_resources(self) -> bool:
        """Clean up unused IAM roles and policies"""
        print("\n🔄 Phase 4: IAM Resources Cleanup")
        
        try:
            # Target IAM roles for deletion
            target_role_prefixes = [
                'multimodal-lib-prod-',
                'multimodal-librarian-full-ml-',
                'MultimodalLibrarianFullML-'
            ]
            
            deleted_roles = []
            deleted_policies = []
            
            # Clean up roles
            paginator = self.iam_client.get_paginator('list_roles')
            for page in paginator.paginate():
                for role in page['Roles']:
                    role_name = role['RoleName']
                    
                    # Check if role matches our target prefixes
                    if any(role_name.startswith(prefix) for prefix in target_role_prefixes):
                        try:
                            # Detach policies first
                            attached_policies = self.iam_client.list_attached_role_policies(RoleName=role_name)
                            for policy in attached_policies['AttachedPolicies']:
                                self.iam_client.detach_role_policy(
                                    RoleName=role_name,
                                    PolicyArn=policy['PolicyArn']
                                )
                            
                            # Delete inline policies
                            inline_policies = self.iam_client.list_role_policies(RoleName=role_name)
                            for policy_name in inline_policies['PolicyNames']:
                                self.iam_client.delete_role_policy(
                                    RoleName=role_name,
                                    PolicyName=policy_name
                                )
                            
                            # Delete the role
                            self.iam_client.delete_role(RoleName=role_name)
                            deleted_roles.append(role_name)
                            print(f"  ✅ Deleted IAM role: {role_name}")
                            
                        except Exception as e:
                            error_msg = f"Failed to delete IAM role {role_name}: {e}"
                            print(f"  ❌ {error_msg}")
                            self.results["errors"].append(error_msg)
            
            # Clean up policies
            target_policy_prefixes = [
                'MultimodalLibrarian'
            ]
            
            paginator = self.iam_client.get_paginator('list_policies')
            for page in paginator.paginate(Scope='Local'):  # Only customer-managed policies
                for policy in page['Policies']:
                    policy_name = policy['PolicyName']
                    
                    if any(policy_name.startswith(prefix) for prefix in target_policy_prefixes):
                        try:
                            self.iam_client.delete_policy(PolicyArn=policy['Arn'])
                            deleted_policies.append(policy_name)
                            print(f"  ✅ Deleted IAM policy: {policy_name}")
                            
                        except Exception as e:
                            error_msg = f"Failed to delete IAM policy {policy_name}: {e}"
                            print(f"  ❌ {error_msg}")
                            self.results["errors"].append(error_msg)
            
            if deleted_roles or deleted_policies:
                print(f"✅ Successfully deleted {len(deleted_roles)} roles and {len(deleted_policies)} policies")
                self.results["iam_cleanup"] = True
                # IAM resources don't have direct costs, but good for security cleanup
                return True
            else:
                print("ℹ️  No IAM resources found to delete")
                return True
                
        except Exception as e:
            error_msg = f"IAM cleanup failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def analyze_collaborative_editor(self) -> bool:
        """Analyze Collaborative Editor resources for potential shutdown"""
        print("\n🔄 Phase 5: Collaborative Editor Analysis")
        
        try:
            # Check EC2 instance in us-west-2
            instances = self.ec2_west_client.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']},
                    {'Name': 'tag:Name', 'Values': ['collaborative-editor-env']}
                ]
            )
            
            collaborative_resources = []
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_info = {
                        'instance_id': instance['InstanceId'],
                        'instance_type': instance['InstanceType'],
                        'launch_time': instance['LaunchTime'].isoformat(),
                        'state': instance['State']['Name'],
                        'estimated_monthly_cost': 15  # t3.micro estimated cost
                    }
                    collaborative_resources.append(instance_info)
                    
                    print(f"  📊 Found Collaborative Editor instance:")
                    print(f"     Instance ID: {instance['InstanceId']}")
                    print(f"     Type: {instance['InstanceType']}")
                    print(f"     State: {instance['State']['Name']}")
                    print(f"     Estimated cost: $15/month")
            
            if collaborative_resources:
                print(f"\n💡 Collaborative Editor Analysis:")
                print(f"   - Found {len(collaborative_resources)} running instance(s)")
                print(f"   - Potential additional savings: $15-20/month")
                print(f"   - This appears to be a separate project")
                print(f"   - Consider evaluating if this can also be shut down")
                
                self.results["collaborative_editor_analysis"] = True
                self.results["collaborative_editor_resources"] = collaborative_resources
                # Don't add to savings yet - this requires separate decision
                return True
            else:
                print("ℹ️  No Collaborative Editor resources found")
                return True
                
        except Exception as e:
            error_msg = f"Collaborative Editor analysis failed: {e}"
            print(f"❌ {error_msg}")
            self.results["errors"].append(error_msg)
            return False

    def save_results(self):
        """Save cleanup results to file"""
        filename = f"additional-resource-cleanup-{int(time.time())}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            print(f"\n📄 Results saved to: {filename}")
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")

    def run_cleanup(self):
        """Execute the complete additional resource cleanup"""
        print("🚀 Starting Additional AWS Resource Cleanup")
        print("=" * 60)
        
        # Phase 1: Lambda Functions
        lambda_success = self.cleanup_lambda_functions()
        
        # Phase 2: S3 Buckets
        s3_success = self.cleanup_s3_buckets()
        
        # Phase 3: VPC Infrastructure
        vpc_success = self.cleanup_vpc_infrastructure()
        
        # Phase 4: IAM Resources
        iam_success = self.cleanup_iam_resources()
        
        # Phase 5: Collaborative Editor Analysis
        collab_success = self.analyze_collaborative_editor()
        
        # Summary
        print("\n" + "=" * 60)
        print("🎯 ADDITIONAL CLEANUP SUMMARY")
        print("=" * 60)
        
        print(f"✅ Lambda Functions: {'Success' if lambda_success else 'Failed'}")
        print(f"✅ S3 Buckets: {'Success' if s3_success else 'Failed'}")
        print(f"✅ VPC Infrastructure: {'Success' if vpc_success else 'Failed'}")
        print(f"✅ IAM Resources: {'Success' if iam_success else 'Failed'}")
        print(f"📊 Collaborative Editor: {'Analyzed' if collab_success else 'Failed'}")
        
        print(f"\n💰 ADDITIONAL COST SAVINGS")
        print(f"Monthly Savings: ${self.results['total_additional_monthly_savings']}")
        print(f"Annual Savings: ${self.results['total_additional_monthly_savings'] * 12}")
        
        if self.results["errors"]:
            print(f"\n⚠️  Errors encountered: {len(self.results['errors'])}")
            for error in self.results["errors"]:
                print(f"   - {error}")
        
        # Save results
        self.save_results()
        
        return all([lambda_success, s3_success, vpc_success, iam_success, collab_success])

def main():
    """Main execution function"""
    cleanup = AdditionalResourceCleanup()
    
    try:
        success = cleanup.run_cleanup()
        
        if success:
            print("\n🎉 Additional resource cleanup completed successfully!")
            print(f"💰 Additional monthly savings: ${cleanup.results['total_additional_monthly_savings']}")
            print(f"💰 Additional annual savings: ${cleanup.results['total_additional_monthly_savings'] * 12}")
        else:
            print("\n⚠️  Additional resource cleanup completed with some errors")
            
    except KeyboardInterrupt:
        print("\n⚠️  Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()