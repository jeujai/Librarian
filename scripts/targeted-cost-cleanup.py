#!/usr/bin/env python3
"""
Targeted Cost Cleanup Script
Focus on the biggest cost drivers from the billing analysis:
1. Amazon Neptune: $115.79
2. Amazon ECS: $100.56  
3. EC2 - Other: $93.41
4. Amazon VPC: $69.64
5. Amazon Elastic Load Balancing: $29.64
6. Amazon ElastiCache: $27.29
7. CloudFront Flat-Rate Plans: $15.00
8. Amazon OpenSearch: $13.09
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

def force_delete_neptune():
    """Force delete Neptune cluster and instances"""
    log_action("🗑️ Force deleting Neptune resources...")
    
    try:
        neptune = boto3.client('neptune', region_name='us-east-1')
        
        # First, start the cluster if it's stopped
        try:
            neptune.start_db_cluster(DBClusterIdentifier='multimodal-lib-prod-neptune')
            log_action("Started Neptune cluster to enable deletion")
            time.sleep(60)  # Wait for cluster to start
        except ClientError as e:
            log_action(f"Cluster may already be starting: {e}")
        
        # Delete the instance first
        try:
            neptune.delete_db_instance(
                DBInstanceIdentifier='tf-20260122080926495300000003',
                SkipFinalSnapshot=True
            )
            log_action("Deleted Neptune instance")
            time.sleep(120)  # Wait for instance deletion
        except ClientError as e:
            log_action(f"Error deleting Neptune instance: {e}")
        
        # Now delete the cluster
        try:
            neptune.delete_db_cluster(
                DBClusterIdentifier='multimodal-lib-prod-neptune',
                SkipFinalSnapshot=True
            )
            log_action("Deleted Neptune cluster")
            return 115.79
        except ClientError as e:
            log_action(f"Error deleting Neptune cluster: {e}")
            return 0
            
    except ClientError as e:
        log_action(f"Error accessing Neptune: {e}")
        return 0

def cleanup_ecs_fargate_tasks():
    """Find and stop all ECS Fargate tasks"""
    log_action("🗑️ Cleaning up ECS Fargate tasks...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            ecs = boto3.client('ecs', region_name=region)
            
            # List all clusters
            clusters = ecs.list_clusters()
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                log_action(f"Checking cluster: {cluster_name} in {region}")
                
                # List all tasks in the cluster
                tasks = ecs.list_tasks(cluster=cluster_arn)
                
                for task_arn in tasks['taskArns']:
                    task_id = task_arn.split('/')[-1]
                    log_action(f"Found task: {task_id}")
                    
                    try:
                        ecs.stop_task(
                            cluster=cluster_arn,
                            task=task_arn,
                            reason='Cost optimization cleanup'
                        )
                        log_action(f"Stopped task: {task_id}")
                        total_savings += 5  # Estimate per task
                    except ClientError as e:
                        log_action(f"Error stopping task {task_id}: {e}")
                
                # List and delete services
                services = ecs.list_services(cluster=cluster_arn)
                for service_arn in services['serviceArns']:
                    service_name = service_arn.split('/')[-1]
                    log_action(f"Found service: {service_name}")
                    
                    try:
                        # Scale to 0 first
                        ecs.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        log_action(f"Scaled service {service_name} to 0")
                        time.sleep(30)
                        
                        # Delete service
                        ecs.delete_service(
                            cluster=cluster_arn,
                            service=service_arn
                        )
                        log_action(f"Deleted service: {service_name}")
                        total_savings += 50  # Estimate per service
                    except ClientError as e:
                        log_action(f"Error deleting service {service_name}: {e}")
                
                # Delete cluster
                try:
                    ecs.delete_cluster(cluster=cluster_arn)
                    log_action(f"Deleted cluster: {cluster_name}")
                except ClientError as e:
                    log_action(f"Error deleting cluster {cluster_name}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing ECS in {region}: {e}")
    
    return total_savings

def cleanup_ec2_other_resources():
    """Clean up EC2 'Other' resources like EBS volumes, snapshots, etc."""
    log_action("🗑️ Cleaning up EC2 'Other' resources...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            
            # Clean up unattached EBS volumes
            volumes = ec2.describe_volumes(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )
            
            for volume in volumes['Volumes']:
                volume_id = volume['VolumeId']
                size = volume['Size']
                log_action(f"Found unattached EBS volume: {volume_id} ({size}GB) in {region}")
                
                try:
                    ec2.delete_volume(VolumeId=volume_id)
                    log_action(f"Deleted EBS volume: {volume_id}")
                    total_savings += size * 0.10  # Estimate $0.10/GB/month
                except ClientError as e:
                    log_action(f"Error deleting volume {volume_id}: {e}")
            
            # Clean up old snapshots
            snapshots = ec2.describe_snapshots(OwnerIds=['self'])
            
            for snapshot in snapshots['Snapshots']:
                snapshot_id = snapshot['SnapshotId']
                # Only delete snapshots older than 30 days
                snapshot_date = snapshot['StartTime'].replace(tzinfo=None)
                age_days = (datetime.now() - snapshot_date).days
                
                if age_days > 30:
                    log_action(f"Found old snapshot: {snapshot_id} ({age_days} days old)")
                    try:
                        ec2.delete_snapshot(SnapshotId=snapshot_id)
                        log_action(f"Deleted old snapshot: {snapshot_id}")
                        total_savings += 1  # Estimate
                    except ClientError as e:
                        log_action(f"Error deleting snapshot {snapshot_id}: {e}")
            
            # Clean up unused Elastic IPs
            addresses = ec2.describe_addresses()
            
            for address in addresses['Addresses']:
                if 'InstanceId' not in address and 'NetworkInterfaceId' not in address:
                    allocation_id = address.get('AllocationId')
                    public_ip = address.get('PublicIp')
                    log_action(f"Found unused Elastic IP: {public_ip}")
                    
                    try:
                        if allocation_id:
                            ec2.release_address(AllocationId=allocation_id)
                        else:
                            ec2.release_address(PublicIp=public_ip)
                        log_action(f"Released Elastic IP: {public_ip}")
                        total_savings += 3.65  # $0.005/hour * 24 * 30
                    except ClientError as e:
                        log_action(f"Error releasing Elastic IP {public_ip}: {e}")
                        
        except ClientError as e:
            log_action(f"Error accessing EC2 in {region}: {e}")
    
    return total_savings

def cleanup_vpc_resources():
    """Clean up VPC resources like NAT Gateways, VPC Endpoints"""
    log_action("🗑️ Cleaning up VPC resources...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            ec2 = boto3.client('ec2', region_name=region)
            
            # Delete NAT Gateways
            nat_gateways = ec2.describe_nat_gateways(
                Filters=[{'Name': 'state', 'Values': ['available']}]
            )
            
            for nat_gw in nat_gateways['NatGateways']:
                nat_gw_id = nat_gw['NatGatewayId']
                log_action(f"Found NAT Gateway: {nat_gw_id} in {region}")
                
                try:
                    ec2.delete_nat_gateway(NatGatewayId=nat_gw_id)
                    log_action(f"Deleted NAT Gateway: {nat_gw_id}")
                    total_savings += 45.60  # $0.045/hour * 24 * 30 + data processing
                except ClientError as e:
                    log_action(f"Error deleting NAT Gateway {nat_gw_id}: {e}")
            
            # Delete VPC Endpoints
            vpc_endpoints = ec2.describe_vpc_endpoints()
            
            for endpoint in vpc_endpoints['VpcEndpoints']:
                endpoint_id = endpoint['VpcEndpointId']
                service_name = endpoint['ServiceName']
                log_action(f"Found VPC Endpoint: {endpoint_id} ({service_name}) in {region}")
                
                try:
                    ec2.delete_vpc_endpoint(VpcEndpointId=endpoint_id)
                    log_action(f"Deleted VPC Endpoint: {endpoint_id}")
                    total_savings += 7.30  # Estimate per endpoint
                except ClientError as e:
                    log_action(f"Error deleting VPC Endpoint {endpoint_id}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing VPC resources in {region}: {e}")
    
    return total_savings

def cleanup_load_balancers():
    """Delete all load balancers"""
    log_action("🗑️ Cleaning up Load Balancers...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            elbv2 = boto3.client('elbv2', region_name=region)
            
            # List and delete ALBs/NLBs
            load_balancers = elbv2.describe_load_balancers()
            
            for lb in load_balancers['LoadBalancers']:
                lb_arn = lb['LoadBalancerArn']
                lb_name = lb['LoadBalancerName']
                lb_type = lb['Type']
                log_action(f"Found {lb_type.upper()}: {lb_name} in {region}")
                
                try:
                    elbv2.delete_load_balancer(LoadBalancerArn=lb_arn)
                    log_action(f"Deleted {lb_type.upper()}: {lb_name}")
                    total_savings += 22.56 if lb_type == 'application' else 16.43  # Monthly cost
                except ClientError as e:
                    log_action(f"Error deleting {lb_type.upper()} {lb_name}: {e}")
            
            # Clean up target groups
            target_groups = elbv2.describe_target_groups()
            
            for tg in target_groups['TargetGroups']:
                tg_arn = tg['TargetGroupArn']
                tg_name = tg['TargetGroupName']
                log_action(f"Found Target Group: {tg_name} in {region}")
                
                try:
                    elbv2.delete_target_group(TargetGroupArn=tg_arn)
                    log_action(f"Deleted Target Group: {tg_name}")
                except ClientError as e:
                    log_action(f"Error deleting Target Group {tg_name}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing Load Balancers in {region}: {e}")
    
    return total_savings

def cleanup_elasticache():
    """Delete ElastiCache clusters"""
    log_action("🗑️ Cleaning up ElastiCache...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            elasticache = boto3.client('elasticache', region_name=region)
            
            # Delete cache clusters
            clusters = elasticache.describe_cache_clusters()
            
            for cluster in clusters['CacheClusters']:
                cluster_id = cluster['CacheClusterId']
                node_type = cluster['CacheNodeType']
                log_action(f"Found ElastiCache cluster: {cluster_id} ({node_type}) in {region}")
                
                try:
                    elasticache.delete_cache_cluster(CacheClusterId=cluster_id)
                    log_action(f"Deleted ElastiCache cluster: {cluster_id}")
                    total_savings += 27.29  # From billing data
                except ClientError as e:
                    log_action(f"Error deleting ElastiCache cluster {cluster_id}: {e}")
            
            # Delete replication groups
            replication_groups = elasticache.describe_replication_groups()
            
            for rg in replication_groups['ReplicationGroups']:
                rg_id = rg['ReplicationGroupId']
                log_action(f"Found ElastiCache replication group: {rg_id} in {region}")
                
                try:
                    elasticache.delete_replication_group(ReplicationGroupId=rg_id)
                    log_action(f"Deleted ElastiCache replication group: {rg_id}")
                    total_savings += 20  # Estimate
                except ClientError as e:
                    log_action(f"Error deleting replication group {rg_id}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing ElastiCache in {region}: {e}")
    
    return total_savings

def cleanup_opensearch():
    """Delete OpenSearch domains"""
    log_action("🗑️ Cleaning up OpenSearch domains...")
    
    regions = ['us-east-1', 'us-west-2']
    total_savings = 0
    
    for region in regions:
        try:
            opensearch = boto3.client('opensearch', region_name=region)
            
            # List and delete domains
            domains = opensearch.list_domain_names()
            
            for domain in domains['DomainNames']:
                domain_name = domain['DomainName']
                log_action(f"Found OpenSearch domain: {domain_name} in {region}")
                
                try:
                    opensearch.delete_domain(DomainName=domain_name)
                    log_action(f"Deleted OpenSearch domain: {domain_name}")
                    total_savings += 13.09  # From billing data
                except ClientError as e:
                    log_action(f"Error deleting OpenSearch domain {domain_name}: {e}")
                    
        except ClientError as e:
            log_action(f"Error accessing OpenSearch in {region}: {e}")
    
    return total_savings

def main():
    """Main cleanup function"""
    log_action("🚀 Starting Targeted Cost Cleanup")
    log_action("Focusing on the biggest cost drivers from billing analysis")
    
    total_savings = 0
    savings_breakdown = {}
    
    # 1. Neptune ($115.79) - Biggest cost
    log_action("=" * 50)
    savings_breakdown['Neptune'] = force_delete_neptune()
    total_savings += savings_breakdown['Neptune']
    
    # 2. ECS ($100.56) - Second biggest
    log_action("=" * 50)
    savings_breakdown['ECS'] = cleanup_ecs_fargate_tasks()
    total_savings += savings_breakdown['ECS']
    
    # 3. EC2 Other ($93.41) - Third biggest
    log_action("=" * 50)
    savings_breakdown['EC2_Other'] = cleanup_ec2_other_resources()
    total_savings += savings_breakdown['EC2_Other']
    
    # 4. VPC ($69.64) - Fourth biggest
    log_action("=" * 50)
    savings_breakdown['VPC'] = cleanup_vpc_resources()
    total_savings += savings_breakdown['VPC']
    
    # 5. Load Balancers ($29.64)
    log_action("=" * 50)
    savings_breakdown['Load_Balancers'] = cleanup_load_balancers()
    total_savings += savings_breakdown['Load_Balancers']
    
    # 6. ElastiCache ($27.29)
    log_action("=" * 50)
    savings_breakdown['ElastiCache'] = cleanup_elasticache()
    total_savings += savings_breakdown['ElastiCache']
    
    # 7. OpenSearch ($13.09)
    log_action("=" * 50)
    savings_breakdown['OpenSearch'] = cleanup_opensearch()
    total_savings += savings_breakdown['OpenSearch']
    
    # Generate final report
    original_cost = 516.91
    estimated_new_cost = max(0, original_cost - total_savings)
    
    report = {
        'cleanup_timestamp': datetime.now().isoformat(),
        'original_monthly_cost': original_cost,
        'estimated_monthly_savings': total_savings,
        'estimated_new_monthly_cost': estimated_new_cost,
        'savings_breakdown': savings_breakdown,
        'remaining_estimated_costs': {
            'CloudFront_Flat_Rate': 15.00,
            'RDS': 9.47,
            'EC2_Compute': 7.96,
            'AWS_WAF': 4.50,
            'ECR': 2.99,
            'Secrets_Manager': 2.08,
            'CloudWatch': 2.19,
            'Tax': 22.63,
            'Other_Small': 5.00
        },
        'target_achieved': estimated_new_cost < 123.67,
        'notes': [
            "CloudFront flat-rate plans may need manual cancellation",
            "Some resources may have dependencies preventing immediate deletion",
            "Monitor billing console over next 24-48 hours for actual savings",
            "Consider canceling CloudFront flat-rate plans manually if not needed"
        ]
    }
    
    # Save report
    report_file = f"targeted-cost-cleanup-report-{int(time.time())}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    log_action("=" * 50)
    log_action("📊 Targeted Cost Cleanup Summary:")
    log_action(f"Original monthly cost: ${report['original_monthly_cost']}")
    log_action(f"Estimated monthly savings: ${report['estimated_monthly_savings']:.2f}")
    log_action(f"Estimated new monthly cost: ${report['estimated_new_monthly_cost']:.2f}")
    log_action(f"Target achieved: {report['target_achieved']}")
    log_action(f"Report saved to: {report_file}")
    
    if report['target_achieved']:
        log_action("✅ Success: Monthly cost should now be under $123.67")
    else:
        log_action("⚠️  Additional cleanup may be needed to reach target")
        log_action("Consider manually canceling CloudFront flat-rate plans")

if __name__ == "__main__":
    main()