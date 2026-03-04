#!/usr/bin/env python3
"""
Final Manual AWS Cleanup Script
Cleans up remaining resources identified after comprehensive cost optimization.
Potential additional savings: $15-20/month ($180-240/year)
"""

import boto3
import json
import time
from datetime import datetime
from botocore.exceptions import ClientError

def log_action(action, resource, status, details=None):
    """Log cleanup actions"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "resource": resource,
        "status": status
    }
    if details:
        entry["details"] = details
    print(f"[{entry['timestamp']}] {action}: {resource} - {status}")
    return entry

def cleanup_elastic_ips():
    """Release unattached Elastic IPs - $7.30/month savings"""
    print("\n=== CLEANING UP UNATTACHED ELASTIC IPS ===")
    results = []
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # List of unattached IPs identified in analysis
    unattached_ips = ['3.233.193.206', '52.202.142.217']
    
    try:
        # Get all Elastic IPs
        response = ec2.describe_addresses()
        
        for address in response['Addresses']:
            public_ip = address['PublicIp']
            
            if public_ip in unattached_ips:
                # Check if it's actually unattached
                if 'InstanceId' not in address and 'NetworkInterfaceId' not in address:
                    try:
                        print(f"Releasing unattached Elastic IP: {public_ip}")
                        ec2.release_address(PublicIp=public_ip)
                        results.append(log_action("release_elastic_ip", public_ip, "success"))
                        time.sleep(1)  # Rate limiting
                    except ClientError as e:
                        results.append(log_action("release_elastic_ip", public_ip, "error", str(e)))
                else:
                    results.append(log_action("release_elastic_ip", public_ip, "skipped", "attached"))
    
    except ClientError as e:
        results.append(log_action("list_elastic_ips", "all", "error", str(e)))
    
    return results

def cleanup_legacy_lambda_functions():
    """Delete old Lambda functions from 2018 - $5/month savings"""
    print("\n=== CLEANING UP LEGACY LAMBDA FUNCTIONS ===")
    results = []
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Legacy functions identified in analysis
    legacy_functions = [
        'GetBizRule',
        'GetBiiizRule', 
        'GetBusinessRule',
        'SavePerson',
        'SaveBusinessRule'
    ]
    
    for function_name in legacy_functions:
        try:
            # Check if function exists and get details
            response = lambda_client.get_function(FunctionName=function_name)
            last_modified = response['Configuration']['LastModified']
            
            # Confirm it's from 2018 (safety check)
            if '2018-' in last_modified:
                print(f"Deleting legacy Lambda function: {function_name} (last modified: {last_modified})")
                lambda_client.delete_function(FunctionName=function_name)
                results.append(log_action("delete_lambda", function_name, "success", f"last_modified: {last_modified}"))
                time.sleep(1)  # Rate limiting
            else:
                results.append(log_action("delete_lambda", function_name, "skipped", f"not_legacy: {last_modified}"))
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                results.append(log_action("delete_lambda", function_name, "not_found"))
            else:
                results.append(log_action("delete_lambda", function_name, "error", str(e)))
    
    return results

def cleanup_stopped_ec2_instance():
    """Terminate stopped Neo4j EC2 instance - $8/month savings"""
    print("\n=== CLEANING UP STOPPED EC2 INSTANCE ===")
    results = []
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    instance_id = 'i-0255d25fd1950ed2d'  # Stopped Neo4j instance
    
    try:
        # Get instance details
        response = ec2.describe_instances(InstanceIds=[instance_id])
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                state = instance['State']['Name']
                instance_type = instance['InstanceType']
                
                # Get tags for verification
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                
                if state == 'stopped' and tags.get('Component') == 'neo4j-simple':
                    print(f"Terminating stopped Neo4j instance: {instance_id} ({instance_type})")
                    ec2.terminate_instances(InstanceIds=[instance_id])
                    results.append(log_action("terminate_instance", instance_id, "success", 
                                             f"type: {instance_type}, component: neo4j-simple"))
                else:
                    results.append(log_action("terminate_instance", instance_id, "skipped", 
                                             f"state: {state}, tags: {tags}"))
    
    except ClientError as e:
        results.append(log_action("terminate_instance", instance_id, "error", str(e)))
    
    return results

def cleanup_cloudtrail_s3_bucket():
    """Clean up CloudTrail S3 bucket with versioned objects - $0.50/month savings"""
    print("\n=== CLEANING UP CLOUDTRAIL S3 BUCKET ===")
    results = []
    
    s3 = boto3.client('s3', region_name='us-east-1')
    bucket_name = 'multimodal-lib-prod-cloudtrail-logs-50fcb7c1'
    
    try:
        # First, delete all object versions
        print(f"Listing object versions in bucket: {bucket_name}")
        
        # List all object versions
        paginator = s3.get_paginator('list_object_versions')
        pages = paginator.paginate(Bucket=bucket_name)
        
        delete_keys = []
        for page in pages:
            # Add versions
            if 'Versions' in page:
                for version in page['Versions']:
                    delete_keys.append({
                        'Key': version['Key'],
                        'VersionId': version['VersionId']
                    })
            
            # Add delete markers
            if 'DeleteMarkers' in page:
                for marker in page['DeleteMarkers']:
                    delete_keys.append({
                        'Key': marker['Key'],
                        'VersionId': marker['VersionId']
                    })
        
        # Delete objects in batches
        if delete_keys:
            print(f"Deleting {len(delete_keys)} object versions...")
            
            # Process in batches of 1000 (AWS limit)
            for i in range(0, len(delete_keys), 1000):
                batch = delete_keys[i:i+1000]
                
                response = s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': batch}
                )
                
                if 'Deleted' in response:
                    results.append(log_action("delete_s3_objects", bucket_name, 
                                             f"deleted_{len(response['Deleted'])}_objects"))
                
                if 'Errors' in response:
                    for error in response['Errors']:
                        results.append(log_action("delete_s3_objects", bucket_name, "error", 
                                                 f"key: {error['Key']}, error: {error['Message']}"))
                
                time.sleep(0.1)  # Rate limiting
        
        # Now delete the bucket
        print(f"Deleting empty bucket: {bucket_name}")
        s3.delete_bucket(Bucket=bucket_name)
        results.append(log_action("delete_s3_bucket", bucket_name, "success"))
        
    except ClientError as e:
        results.append(log_action("cleanup_s3_bucket", bucket_name, "error", str(e)))
    
    return results

def cleanup_unused_security_groups():
    """Clean up unused security groups identified in final cleanup"""
    print("\n=== CLEANING UP UNUSED SECURITY GROUPS ===")
    results = []
    
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    # Security groups identified as unused in previous cleanup
    unused_sgs = [
        'sg-0ef638d48668fcbb6',  # multimodal-lib-prod-vpc-endpoints
        'sg-0aa3c36bef3c376e9',  # vpc-endpoints-1768004681
        'sg-046d0c09acd59d83d',  # neo4j-security-group-simple
        'sg-0cee28bdb3ec57732',  # multimodal-lib-prod-opensearch
        'sg-0231498cba0c6b983'   # multimodal-lib-prod-neptune
    ]
    
    for sg_id in unused_sgs:
        try:
            # Get security group details
            response = ec2.describe_security_groups(GroupIds=[sg_id])
            sg = response['SecurityGroups'][0]
            
            print(f"Deleting unused security group: {sg_id} ({sg['GroupName']})")
            ec2.delete_security_group(GroupId=sg_id)
            results.append(log_action("delete_security_group", sg_id, "success", sg['GroupName']))
            time.sleep(1)  # Rate limiting
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidGroup.NotFound':
                results.append(log_action("delete_security_group", sg_id, "not_found"))
            elif 'DependencyViolation' in str(e):
                results.append(log_action("delete_security_group", sg_id, "has_dependencies"))
            else:
                results.append(log_action("delete_security_group", sg_id, "error", str(e)))
    
    return results

def cleanup_small_s3_buckets():
    """Clean up remaining small S3 buckets"""
    print("\n=== CLEANING UP SMALL S3 BUCKETS ===")
    results = []
    
    s3 = boto3.client('s3')
    
    # Small buckets identified in analysis
    small_buckets = [
        'cdk-hnb659fds-assets-591222106065-us-east-1',
        'elasticbeanstalk-us-west-2-591222106065'
    ]
    
    for bucket_name in small_buckets:
        try:
            # Check if bucket exists and get region
            response = s3.head_bucket(Bucket=bucket_name)
            
            # Delete all objects first
            s3_resource = boto3.resource('s3')
            bucket = s3_resource.Bucket(bucket_name)
            
            print(f"Deleting objects in bucket: {bucket_name}")
            bucket.objects.all().delete()
            
            # Delete the bucket
            print(f"Deleting bucket: {bucket_name}")
            s3.delete_bucket(Bucket=bucket_name)
            results.append(log_action("delete_s3_bucket", bucket_name, "success"))
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                results.append(log_action("delete_s3_bucket", bucket_name, "not_found"))
            else:
                results.append(log_action("delete_s3_bucket", bucket_name, "error", str(e)))
    
    return results

def main():
    """Execute final manual cleanup"""
    print("🧹 FINAL MANUAL AWS CLEANUP")
    print("=" * 50)
    print("Potential additional savings: $15-20/month ($180-240/year)")
    print("=" * 50)
    
    all_results = []
    estimated_savings = 0
    
    # 1. Release unattached Elastic IPs ($7.30/month)
    eip_results = cleanup_elastic_ips()
    all_results.extend(eip_results)
    successful_eips = len([r for r in eip_results if r['status'] == 'success'])
    estimated_savings += successful_eips * 3.65  # $3.65 per EIP
    
    # 2. Delete legacy Lambda functions ($5/month)
    lambda_results = cleanup_legacy_lambda_functions()
    all_results.extend(lambda_results)
    successful_lambdas = len([r for r in lambda_results if r['status'] == 'success'])
    estimated_savings += successful_lambdas * 1.0  # $1 per function
    
    # 3. Terminate stopped EC2 instance ($8/month)
    ec2_results = cleanup_stopped_ec2_instance()
    all_results.extend(ec2_results)
    successful_ec2 = len([r for r in ec2_results if r['status'] == 'success'])
    estimated_savings += successful_ec2 * 8.0  # $8 for t3.medium
    
    # 4. Clean up CloudTrail S3 bucket ($0.50/month)
    s3_cloudtrail_results = cleanup_cloudtrail_s3_bucket()
    all_results.extend(s3_cloudtrail_results)
    successful_cloudtrail = len([r for r in s3_cloudtrail_results if r['status'] == 'success' and 'bucket' in r['action']])
    estimated_savings += successful_cloudtrail * 0.5  # $0.50 for CloudTrail bucket
    
    # 5. Clean up unused security groups (no direct cost but good hygiene)
    sg_results = cleanup_unused_security_groups()
    all_results.extend(sg_results)
    
    # 6. Clean up small S3 buckets (minimal cost but good hygiene)
    s3_small_results = cleanup_small_s3_buckets()
    all_results.extend(s3_small_results)
    
    # Generate summary report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": datetime.now().isoformat(),
        "cleanup_type": "final_manual_cleanup",
        "estimated_monthly_savings": estimated_savings,
        "estimated_annual_savings": estimated_savings * 12,
        "resources_processed": len(all_results),
        "successful_actions": len([r for r in all_results if r['status'] == 'success']),
        "failed_actions": len([r for r in all_results if r['status'] == 'error']),
        "detailed_results": all_results
    }
    
    # Save results
    filename = f"final-manual-cleanup-{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump(report, f, indent=2)
    
    # Print summary
    print("\n" + "=" * 50)
    print("🎉 FINAL MANUAL CLEANUP COMPLETE")
    print("=" * 50)
    print(f"📊 Resources Processed: {report['resources_processed']}")
    print(f"✅ Successful Actions: {report['successful_actions']}")
    print(f"❌ Failed Actions: {report['failed_actions']}")
    print(f"💰 Estimated Monthly Savings: ${estimated_savings:.2f}")
    print(f"💰 Estimated Annual Savings: ${estimated_savings * 12:.2f}")
    print(f"📄 Detailed Report: {filename}")
    
    # Calculate total project savings
    previous_savings = 393.24  # From MAXIMUM_COST_OPTIMIZATION_COMPLETE.md
    total_monthly_savings = previous_savings + estimated_savings
    total_annual_savings = total_monthly_savings * 12
    
    print("\n" + "=" * 50)
    print("🏆 TOTAL PROJECT COST OPTIMIZATION")
    print("=" * 50)
    print(f"Previous Cleanup Savings: ${previous_savings:.2f}/month")
    print(f"Final Manual Cleanup: ${estimated_savings:.2f}/month")
    print(f"🎯 TOTAL MONTHLY SAVINGS: ${total_monthly_savings:.2f}")
    print(f"🎯 TOTAL ANNUAL SAVINGS: ${total_annual_savings:.2f}")
    print("=" * 50)
    
    return report

if __name__ == "__main__":
    main()