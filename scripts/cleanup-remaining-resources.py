#!/usr/bin/env python3
"""
Clean up remaining resources found in the scan
"""

import boto3
import json
from datetime import datetime
import sys

def cleanup_remaining_resources():
    session = boto3.Session()
    
    print("🧹 CLEANING UP REMAINING RESOURCES")
    print("=" * 60)
    
    actions_taken = []
    
    # Delete CloudFront distributions (disabled ones costing $15/month)
    print("🔍 DELETING CLOUDFRONT DISTRIBUTIONS...")
    try:
        cloudfront = session.client('cloudfront')
        
        distributions = cloudfront.list_distributions()
        if 'DistributionList' in distributions and 'Items' in distributions['DistributionList']:
            for dist in distributions['DistributionList']['Items']:
                dist_id = dist['Id']
                enabled = dist['Enabled']
                
                print(f"  Found distribution: {dist_id} (Enabled: {enabled})")
                
                if not enabled:  # Only delete disabled distributions
                    try:
                        # Get ETag for deletion
                        config_response = cloudfront.get_distribution_config(Id=dist_id)
                        etag = config_response['ETag']
                        
                        # Delete the distribution
                        cloudfront.delete_distribution(Id=dist_id, IfMatch=etag)
                        actions_taken.append(f"✅ Deleted CloudFront distribution {dist_id}")
                        print(f"    ✅ Deleted distribution {dist_id}")
                        
                    except Exception as e:
                        actions_taken.append(f"❌ Failed to delete CloudFront distribution {dist_id}: {str(e)}")
                        print(f"    ❌ Error deleting {dist_id}: {str(e)}")
                else:
                    print(f"    ⏭️  Skipping enabled distribution {dist_id}")
                    
    except Exception as e:
        print(f"  Error listing CloudFront distributions: {e}")
    
    # Delete empty S3 bucket
    print("\n🔍 DELETING EMPTY S3 BUCKETS...")
    try:
        s3 = session.client('s3')
        
        buckets = s3.list_buckets()
        for bucket in buckets['Buckets']:
            bucket_name = bucket['Name']
            
            try:
                # Check if bucket is empty
                objects = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                
                if 'Contents' not in objects:  # Bucket is empty
                    print(f"  Found empty bucket: {bucket_name}")
                    
                    # Delete the bucket
                    s3.delete_bucket(Bucket=bucket_name)
                    actions_taken.append(f"✅ Deleted empty S3 bucket {bucket_name}")
                    print(f"    ✅ Deleted empty bucket {bucket_name}")
                else:
                    print(f"  Bucket {bucket_name} is not empty, skipping")
                    
            except Exception as e:
                actions_taken.append(f"❌ Failed to delete S3 bucket {bucket_name}: {str(e)}")
                print(f"    ❌ Error with bucket {bucket_name}: {str(e)}")
                
    except Exception as e:
        print(f"  Error listing S3 buckets: {e}")
    
    # Terminate stopped EC2 instances
    print("\n🔍 TERMINATING STOPPED EC2 INSTANCES...")
    regions_to_check = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
    
    for region in regions_to_check:
        try:
            ec2 = session.client('ec2', region_name=region)
            
            instances = ec2.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['stopped']}
                ]
            )
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    instance_type = instance['InstanceType']
                    
                    print(f"  Found stopped instance in {region}: {instance_id} ({instance_type})")
                    
                    try:
                        ec2.terminate_instances(InstanceIds=[instance_id])
                        actions_taken.append(f"✅ Terminated EC2 instance {instance_id} in {region}")
                        print(f"    ✅ Terminated {instance_id}")
                        
                    except Exception as e:
                        actions_taken.append(f"❌ Failed to terminate {instance_id}: {str(e)}")
                        print(f"    ❌ Error terminating {instance_id}: {str(e)}")
                        
        except Exception as e:
            print(f"  Error checking EC2 in {region}: {e}")
    
    # Release unattached Elastic IPs
    print("\n🔍 RELEASING UNATTACHED ELASTIC IPs...")
    for region in regions_to_check:
        try:
            ec2 = session.client('ec2', region_name=region)
            
            addresses = ec2.describe_addresses()
            
            for address in addresses['Addresses']:
                allocation_id = address.get('AllocationId', '')
                public_ip = address.get('PublicIp', '')
                instance_id = address.get('InstanceId', '')
                
                if not instance_id:  # Unattached EIP
                    print(f"  Found unattached EIP in {region}: {public_ip}")
                    
                    try:
                        if allocation_id:
                            ec2.release_address(AllocationId=allocation_id)
                        else:
                            ec2.release_address(PublicIp=public_ip)
                        
                        actions_taken.append(f"✅ Released Elastic IP {public_ip} in {region}")
                        print(f"    ✅ Released {public_ip}")
                        
                    except Exception as e:
                        actions_taken.append(f"❌ Failed to release EIP {public_ip}: {str(e)}")
                        print(f"    ❌ Error releasing {public_ip}: {str(e)}")
                        
        except Exception as e:
            print(f"  Error checking EIPs in {region}: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 CLEANUP SUMMARY:")
    
    success_count = len([action for action in actions_taken if action.startswith('✅')])
    error_count = len([action for action in actions_taken if action.startswith('❌')])
    
    print(f"  ✅ Successful actions: {success_count}")
    print(f"  ❌ Failed actions: {error_count}")
    
    if actions_taken:
        print(f"\n📝 ACTIONS TAKEN:")
        for action in actions_taken:
            print(f"  {action}")
    else:
        print(f"\n❓ No resources found to clean up")
    
    # Save log
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f"cleanup-remaining-{timestamp}.json"
    
    with open(log_filename, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'actions_taken': actions_taken,
            'success_count': success_count,
            'error_count': error_count
        }, f, indent=2)
    
    print(f"\n📝 Cleanup log saved to: {log_filename}")
    
    return success_count > 0

if __name__ == "__main__":
    success = cleanup_remaining_resources()
    sys.exit(0 if success else 1)