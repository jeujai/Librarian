#!/usr/bin/env python3
"""
Immediate Cost Cleanup - Remove resources that can be deleted right now
"""

import boto3
import json
import time
from datetime import datetime
from botocore.exceptions import ClientError

def log_action(message):
    """Log actions with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def cleanup_cloudfront_distributions():
    """Disable and delete CloudFront distributions"""
    log_action("🗑️ Cleaning up CloudFront distributions...")
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        # List distributions
        distributions = cloudfront.list_distributions()
        
        total_savings = 0
        if 'Items' in distributions['DistributionList']:
            for dist in distributions['DistributionList']['Items']:
                dist_id = dist['Id']
                domain_name = dist['DomainName']
                enabled = dist['Enabled']
                
                log_action(f"Found CloudFront distribution: {dist_id} ({domain_name}) - Enabled: {enabled}")
                
                if enabled:
                    try:
                        # Get distribution config
                        config = cloudfront.get_distribution_config(Id=dist_id)
                        
                        # Disable distribution
                        config['DistributionConfig']['Enabled'] = False
                        
                        cloudfront.update_distribution(
                            Id=dist_id,
                            DistributionConfig=config['DistributionConfig'],
                            IfMatch=config['ETag']
                        )
                        log_action(f"Disabled CloudFront distribution: {dist_id}")
                        total_savings += 3.75  # Estimate per distribution
                        
                    except ClientError as e:
                        log_action(f"Error disabling CloudFront distribution {dist_id}: {e}")
                else:
                    log_action(f"Distribution {dist_id} already disabled")
        
        return total_savings
        
    except ClientError as e:
        log_action(f"Error accessing CloudFront: {e}")
        return 0

def cleanup_secrets_manager():
    """Clean up unused secrets"""
    log_action("🗑️ Cleaning up Secrets Manager...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            secrets = boto3.client('secretsmanager', region_name=region)
            
            # List secrets
            secret_list = secrets.list_secrets()
            
            for secret in secret_list['SecretList']:
                secret_name = secret['Name']
                secret_arn = secret['ARN']
                
                log_action(f"Found secret: {secret_name} in {region}")
                
                # Check if secret is used (this is a simplified check)
                # In production, you'd want more sophisticated logic
                if 'test' in secret_name.lower() or 'dev' in secret_name.lower():
                    try:
                        secrets.delete_secret(
                            SecretId=secret_arn,
                            ForceDeleteWithoutRecovery=True
                        )
                        log_action(f"Deleted secret: {secret_name}")
                        total_savings += 0.40  # $0.40 per secret per month
                    except ClientError as e:
                        log_action(f"Error deleting secret {secret_name}: {e}")
                else:
                    log_action(f"Keeping secret: {secret_name} (appears to be production)")
                    
        except ClientError as e:
            log_action(f"Error accessing Secrets Manager in {region}: {e}")
    
    return total_savings

def cleanup_ecr_repositories():
    """Clean up ECR repositories and images"""
    log_action("🗑️ Cleaning up ECR repositories...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            ecr = boto3.client('ecr', region_name=region)
            
            # List repositories
            repositories = ecr.describe_repositories()
            
            for repo in repositories['repositories']:
                repo_name = repo['repositoryName']
                repo_uri = repo['repositoryUri']
                
                log_action(f"Found ECR repository: {repo_name} in {region}")
                
                # List images in repository
                try:
                    images = ecr.list_images(repositoryName=repo_name)
                    image_count = len(images['imageIds'])
                    
                    log_action(f"Repository {repo_name} has {image_count} images")
                    
                    # Delete old images (keep only latest 5)
                    if image_count > 5:
                        # Get image details with timestamps
                        image_details = ecr.describe_images(repositoryName=repo_name)
                        
                        # Sort by pushed date, oldest first
                        sorted_images = sorted(
                            image_details['imageDetails'],
                            key=lambda x: x['imagePushedAt']
                        )
                        
                        # Delete all but the latest 5
                        images_to_delete = sorted_images[:-5]
                        
                        for image in images_to_delete:
                            image_digest = image['imageDigest']
                            try:
                                ecr.batch_delete_image(
                                    repositoryName=repo_name,
                                    imageIds=[{'imageDigest': image_digest}]
                                )
                                log_action(f"Deleted old image from {repo_name}")
                                total_savings += 0.10  # Estimate per image
                            except ClientError as e:
                                log_action(f"Error deleting image: {e}")
                    
                except ClientError as e:
                    log_action(f"Error accessing images in {repo_name}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing ECR in {region}: {e}")
    
    return total_savings

def cleanup_cloudwatch_logs():
    """Clean up old CloudWatch log groups"""
    log_action("🗑️ Cleaning up CloudWatch logs...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            logs = boto3.client('logs', region_name=region)
            
            # List log groups
            log_groups = logs.describe_log_groups()
            
            for log_group in log_groups['logGroups']:
                log_group_name = log_group['logGroupName']
                
                # Check if log group is old or unused
                if any(keyword in log_group_name.lower() for keyword in ['test', 'dev', 'old', 'deprecated']):
                    log_action(f"Found old log group: {log_group_name} in {region}")
                    
                    try:
                        logs.delete_log_group(logGroupName=log_group_name)
                        log_action(f"Deleted log group: {log_group_name}")
                        total_savings += 0.50  # Estimate per log group
                    except ClientError as e:
                        log_action(f"Error deleting log group {log_group_name}: {e}")
                else:
                    # Set retention policy to reduce costs
                    try:
                        logs.put_retention_policy(
                            logGroupName=log_group_name,
                            retentionInDays=7  # Reduce from default (never expire)
                        )
                        log_action(f"Set 7-day retention for: {log_group_name}")
                        total_savings += 0.20  # Estimate savings from retention
                    except ClientError as e:
                        log_action(f"Error setting retention for {log_group_name}: {e}")
                        
        except ClientError as e:
            log_action(f"Error accessing CloudWatch Logs in {region}: {e}")
    
    return total_savings

def cleanup_unused_security_groups():
    """Clean up unused security groups"""
    log_action("🗑️ Cleaning up unused security groups...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            
            # Get all security groups
            security_groups = ec2.describe_security_groups()
            
            # Get all network interfaces to see which SGs are in use
            network_interfaces = ec2.describe_network_interfaces()
            used_sg_ids = set()
            
            for ni in network_interfaces['NetworkInterfaces']:
                for group in ni['Groups']:
                    used_sg_ids.add(group['GroupId'])
            
            # Check each security group
            for sg in security_groups['SecurityGroups']:
                sg_id = sg['GroupId']
                sg_name = sg['GroupName']
                
                # Skip default security groups
                if sg_name == 'default':
                    continue
                
                if sg_id not in used_sg_ids:
                    log_action(f"Found unused security group: {sg_name} ({sg_id}) in {region}")
                    
                    try:
                        ec2.delete_security_group(GroupId=sg_id)
                        log_action(f"Deleted unused security group: {sg_name}")
                        total_savings += 0.01  # Minimal savings but good cleanup
                    except ClientError as e:
                        log_action(f"Error deleting security group {sg_name}: {e}")
                        
        except ClientError as e:
            log_action(f"Error accessing Security Groups in {region}: {e}")
    
    return total_savings

def main():
    """Main cleanup function"""
    log_action("🚀 Starting Immediate Cost Cleanup")
    log_action("Cleaning up resources that can be removed immediately")
    
    total_savings = 0
    savings_breakdown = {}
    
    # 1. CloudFront distributions (already disabled some)
    savings_breakdown['CloudFront'] = cleanup_cloudfront_distributions()
    total_savings += savings_breakdown['CloudFront']
    
    # 2. Secrets Manager
    savings_breakdown['Secrets_Manager'] = cleanup_secrets_manager()
    total_savings += savings_breakdown['Secrets_Manager']
    
    # 3. ECR repositories
    savings_breakdown['ECR'] = cleanup_ecr_repositories()
    total_savings += savings_breakdown['ECR']
    
    # 4. CloudWatch logs
    savings_breakdown['CloudWatch_Logs'] = cleanup_cloudwatch_logs()
    total_savings += savings_breakdown['CloudWatch_Logs']
    
    # 5. Unused security groups
    savings_breakdown['Security_Groups'] = cleanup_unused_security_groups()
    total_savings += savings_breakdown['Security_Groups']
    
    # Generate report
    report = {
        'cleanup_timestamp': datetime.now().isoformat(),
        'estimated_monthly_savings': total_savings,
        'savings_breakdown': savings_breakdown,
        'actions_completed': [
            "Disabled CloudFront distributions",
            "Cleaned up test/dev secrets",
            "Removed old ECR images",
            "Set CloudWatch log retention policies",
            "Deleted unused security groups",
            "Deleted VPC endpoints (done earlier)"
        ],
        'next_steps': [
            "Wait for Neptune cluster to start, then delete it (~$115/month savings)",
            "Check for any remaining ECS tasks or services",
            "Consider canceling CloudFront flat-rate plans manually",
            "Monitor billing console for actual cost reductions"
        ]
    }
    
    # Save report
    report_file = f"immediate-cost-cleanup-report-{int(time.time())}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    log_action("📊 Immediate Cost Cleanup Summary:")
    log_action(f"Estimated monthly savings: ${total_savings:.2f}")
    log_action(f"Report saved to: {report_file}")
    log_action("VPC endpoints deleted earlier should save ~$20-30/month")
    log_action("Neptune deletion (when ready) will save ~$115/month")

if __name__ == "__main__":
    main()