#!/usr/bin/env python3
"""
Final Comprehensive AWS Cleanup Script
Identifies and cleans up remaining AWS resources to minimize costs.
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, List, Any

class FinalAWSCleanup:
    def __init__(self):
        self.regions = ['us-east-1', 'us-west-2']
        self.cleanup_results = {
            'timestamp': datetime.now().isoformat(),
            'total_estimated_savings': 0,
            'resources_cleaned': [],
            'resources_skipped': [],
            'errors': []
        }
    
    def cleanup_collaborative_editor(self) -> Dict[str, Any]:
        """Clean up Collaborative Editor Elastic Beanstalk environment"""
        print("🔄 Cleaning up Collaborative Editor environment...")
        
        try:
            eb_client = boto3.client('elasticbeanstalk', region_name='us-west-2')
            
            # List environments
            environments = eb_client.describe_environments(
                ApplicationName='collaborative-editor'
            )
            
            results = []
            for env in environments.get('Environments', []):
                if env['Status'] != 'Terminated':
                    print(f"  Terminating environment: {env['EnvironmentName']}")
                    
                    # Terminate environment
                    eb_client.terminate_environment(
                        EnvironmentName=env['EnvironmentName']
                    )
                    
                    results.append({
                        'type': 'elastic_beanstalk_environment',
                        'name': env['EnvironmentName'],
                        'status': 'terminating',
                        'estimated_savings': 15
                    })
            
            return {
                'success': True,
                'resources': results,
                'estimated_monthly_savings': 15
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'estimated_monthly_savings': 0
            }
    
    def cleanup_legacy_lambda_functions(self) -> Dict[str, Any]:
        """Clean up old Lambda functions from 2018"""
        print("🔄 Cleaning up legacy Lambda functions...")
        
        legacy_functions = [
            'GetBizRule', 'GetBiiizRule', 'GetBusinessRule',
            'SavePerson', 'SaveBusinessRule'
        ]
        
        results = []
        total_savings = 0
        
        for region in self.regions:
            try:
                lambda_client = boto3.client('lambda', region_name=region)
                
                for func_name in legacy_functions:
                    try:
                        # Check if function exists
                        lambda_client.get_function(FunctionName=func_name)
                        
                        print(f"  Deleting function: {func_name} in {region}")
                        lambda_client.delete_function(FunctionName=func_name)
                        
                        results.append({
                            'type': 'lambda_function',
                            'name': func_name,
                            'region': region,
                            'status': 'deleted'
                        })
                        total_savings += 0.5  # Estimate $0.50/month per function
                        
                    except lambda_client.exceptions.ResourceNotFoundException:
                        # Function doesn't exist, skip
                        continue
                        
            except Exception as e:
                self.cleanup_results['errors'].append(f"Lambda cleanup in {region}: {str(e)}")
        
        return {
            'success': True,
            'resources': results,
            'estimated_monthly_savings': total_savings
        }
    
    def cleanup_stopped_ec2_instances(self) -> Dict[str, Any]:
        """Clean up stopped EC2 instances and their EBS volumes"""
        print("🔄 Cleaning up stopped EC2 instances...")
        
        results = []
        total_savings = 0
        
        for region in self.regions:
            try:
                ec2_client = boto3.client('ec2', region_name=region)
                
                # Get stopped instances
                response = ec2_client.describe_instances(
                    Filters=[
                        {'Name': 'instance-state-name', 'Values': ['stopped']},
                        {'Name': 'tag:Project', 'Values': ['multimodal-librarian']}
                    ]
                )
                
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        instance_id = instance['InstanceId']
                        instance_type = instance['InstanceType']
                        
                        print(f"  Terminating stopped instance: {instance_id} ({instance_type}) in {region}")
                        
                        # Terminate instance
                        ec2_client.terminate_instances(InstanceIds=[instance_id])
                        
                        results.append({
                            'type': 'ec2_instance',
                            'id': instance_id,
                            'instance_type': instance_type,
                            'region': region,
                            'status': 'terminated'
                        })
                        
                        # Estimate savings (EBS storage cost)
                        if instance_type == 't3.medium':
                            total_savings += 8  # ~$8/month for EBS storage
                        
            except Exception as e:
                self.cleanup_results['errors'].append(f"EC2 cleanup in {region}: {str(e)}")
        
        return {
            'success': True,
            'resources': results,
            'estimated_monthly_savings': total_savings
        }
    
    def cleanup_unused_security_groups(self) -> Dict[str, Any]:
        """Clean up unused security groups"""
        print("🔄 Cleaning up unused security groups...")
        
        results = []
        
        for region in self.regions:
            try:
                ec2_client = boto3.client('ec2', region_name=region)
                
                # Get all security groups
                response = ec2_client.describe_security_groups()
                
                for sg in response['SecurityGroups']:
                    # Skip default security groups
                    if sg['GroupName'] == 'default':
                        continue
                    
                    # Check if security group is in use
                    try:
                        # Try to delete (this will fail if in use)
                        if self._is_security_group_unused(ec2_client, sg['GroupId']):
                            print(f"  Deleting unused security group: {sg['GroupName']} in {region}")
                            ec2_client.delete_security_group(GroupId=sg['GroupId'])
                            
                            results.append({
                                'type': 'security_group',
                                'id': sg['GroupId'],
                                'name': sg['GroupName'],
                                'region': region,
                                'status': 'deleted'
                            })
                    except Exception:
                        # Security group is in use, skip
                        continue
                        
            except Exception as e:
                self.cleanup_results['errors'].append(f"Security group cleanup in {region}: {str(e)}")
        
        return {
            'success': True,
            'resources': results,
            'estimated_monthly_savings': 0  # No direct cost savings
        }
    
    def _is_security_group_unused(self, ec2_client, sg_id: str) -> bool:
        """Check if a security group is unused"""
        try:
            # Check if used by instances
            instances = ec2_client.describe_instances(
                Filters=[{'Name': 'instance.group-id', 'Values': [sg_id]}]
            )
            if instances['Reservations']:
                return False
            
            # Check if used by load balancers
            elb_client = boto3.client('elbv2', region_name=ec2_client.meta.region_name)
            lbs = elb_client.describe_load_balancers()
            for lb in lbs['LoadBalancers']:
                if sg_id in lb.get('SecurityGroups', []):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def cleanup_unused_s3_buckets(self) -> Dict[str, Any]:
        """Clean up remaining S3 buckets"""
        print("🔄 Cleaning up unused S3 buckets...")
        
        results = []
        total_savings = 0
        
        try:
            s3_client = boto3.client('s3')
            
            # Buckets to potentially clean up
            cleanup_candidates = [
                'cdk-hnb659fds-assets-591222106065-us-east-1',
                'multimodal-lib-prod-cloudtrail-logs-50fcb7c1'
            ]
            
            for bucket_name in cleanup_candidates:
                try:
                    # Check if bucket exists
                    s3_client.head_bucket(Bucket=bucket_name)
                    
                    # Get bucket size
                    size_gb = self._get_bucket_size(s3_client, bucket_name)
                    
                    if size_gb < 1:  # Only delete small buckets automatically
                        print(f"  Deleting small S3 bucket: {bucket_name}")
                        
                        # Empty bucket first
                        self._empty_s3_bucket(s3_client, bucket_name)
                        
                        # Delete bucket
                        s3_client.delete_bucket(Bucket=bucket_name)
                        
                        results.append({
                            'type': 's3_bucket',
                            'name': bucket_name,
                            'size_gb': size_gb,
                            'status': 'deleted'
                        })
                        total_savings += 0.5  # Small savings
                    else:
                        results.append({
                            'type': 's3_bucket',
                            'name': bucket_name,
                            'size_gb': size_gb,
                            'status': 'skipped_large'
                        })
                        
                except Exception as e:
                    print(f"  Skipping bucket {bucket_name}: {str(e)}")
                    
        except Exception as e:
            self.cleanup_results['errors'].append(f"S3 cleanup: {str(e)}")
        
        return {
            'success': True,
            'resources': results,
            'estimated_monthly_savings': total_savings
        }
    
    def _get_bucket_size(self, s3_client, bucket_name: str) -> float:
        """Get bucket size in GB"""
        try:
            response = s3_client.list_objects_v2(Bucket=bucket_name)
            total_size = sum(obj.get('Size', 0) for obj in response.get('Contents', []))
            return total_size / (1024**3)  # Convert to GB
        except Exception:
            return 0
    
    def _empty_s3_bucket(self, s3_client, bucket_name: str):
        """Empty S3 bucket of all objects"""
        try:
            # Delete all objects
            response = s3_client.list_objects_v2(Bucket=bucket_name)
            if 'Contents' in response:
                objects = [{'Key': obj['Key']} for obj in response['Contents']]
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': objects}
                )
            
            # Delete all versions (if versioned)
            response = s3_client.list_object_versions(Bucket=bucket_name)
            if 'Versions' in response:
                versions = [{'Key': obj['Key'], 'VersionId': obj['VersionId']} 
                           for obj in response['Versions']]
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': versions}
                )
                
        except Exception as e:
            print(f"    Warning: Could not fully empty bucket {bucket_name}: {str(e)}")
    
    def generate_cleanup_report(self) -> str:
        """Generate final cleanup report"""
        timestamp = int(time.time())
        filename = f"final-comprehensive-cleanup-{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(self.cleanup_results, f, indent=2)
        
        return filename
    
    def run_comprehensive_cleanup(self) -> Dict[str, Any]:
        """Run all cleanup operations"""
        print("🚀 Starting Final Comprehensive AWS Cleanup")
        print("=" * 60)
        
        # 1. Collaborative Editor
        collab_result = self.cleanup_collaborative_editor()
        if collab_result['success']:
            self.cleanup_results['resources_cleaned'].extend(collab_result['resources'])
            self.cleanup_results['total_estimated_savings'] += collab_result['estimated_monthly_savings']
        
        # 2. Legacy Lambda Functions
        lambda_result = self.cleanup_legacy_lambda_functions()
        if lambda_result['success']:
            self.cleanup_results['resources_cleaned'].extend(lambda_result['resources'])
            self.cleanup_results['total_estimated_savings'] += lambda_result['estimated_monthly_savings']
        
        # 3. Stopped EC2 Instances
        ec2_result = self.cleanup_stopped_ec2_instances()
        if ec2_result['success']:
            self.cleanup_results['resources_cleaned'].extend(ec2_result['resources'])
            self.cleanup_results['total_estimated_savings'] += ec2_result['estimated_monthly_savings']
        
        # 4. Unused Security Groups
        sg_result = self.cleanup_unused_security_groups()
        if sg_result['success']:
            self.cleanup_results['resources_cleaned'].extend(sg_result['resources'])
        
        # 5. S3 Buckets
        s3_result = self.cleanup_unused_s3_buckets()
        if s3_result['success']:
            self.cleanup_results['resources_cleaned'].extend(s3_result['resources'])
            self.cleanup_results['total_estimated_savings'] += s3_result['estimated_monthly_savings']
        
        # Generate report
        report_file = self.generate_cleanup_report()
        
        print("\n" + "=" * 60)
        print("🎉 Final Comprehensive Cleanup Complete!")
        print(f"💰 Additional Monthly Savings: ${self.cleanup_results['total_estimated_savings']}")
        print(f"📄 Detailed report: {report_file}")
        
        return self.cleanup_results

def main():
    """Main execution function"""
    cleanup = FinalAWSCleanup()
    results = cleanup.run_comprehensive_cleanup()
    
    print(f"\n📊 Summary:")
    print(f"  Resources cleaned: {len(results['resources_cleaned'])}")
    print(f"  Estimated monthly savings: ${results['total_estimated_savings']}")
    print(f"  Estimated annual savings: ${results['total_estimated_savings'] * 12}")
    
    if results['errors']:
        print(f"  Errors encountered: {len(results['errors'])}")
        for error in results['errors']:
            print(f"    - {error}")

if __name__ == "__main__":
    main()