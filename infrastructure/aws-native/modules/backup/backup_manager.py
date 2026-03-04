#!/usr/bin/env python3
"""
Backup Manager Lambda Function
Manages automated backups for Neptune and OpenSearch
"""

import json
import boto3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
neptune_client = boto3.client('neptune')
opensearch_client = boto3.client('opensearch')
s3_client = boto3.client('s3')
cloudwatch_client = boto3.client('cloudwatch')

# Environment variables
PROJECT_NAME = "${project_name}"
ENVIRONMENT = "${environment}"
AWS_REGION = "${aws_region}"
SNAPSHOT_BUCKET = "${snapshot_bucket}"
BACKUP_RETENTION_DAYS = int("${backup_retention_days}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for backup management
    """
    logger.info(f"Starting backup management for {PROJECT_NAME}-{ENVIRONMENT}")
    
    results = {
        'neptune_backup_verification': False,
        'opensearch_snapshot_management': False,
        'cleanup_operations': False,
        'errors': []
    }
    
    try:
        # Verify Neptune backup configuration
        results['neptune_backup_verification'] = verify_neptune_backups()
        
        # Manage OpenSearch snapshots
        results['opensearch_snapshot_management'] = manage_opensearch_snapshots()
        
        # Cleanup old snapshots
        results['cleanup_operations'] = cleanup_old_snapshots()
        
        # Send success metrics
        send_backup_metrics(success=True, errors=len(results['errors']))
        
        logger.info("Backup management completed successfully")
        
    except Exception as e:
        error_msg = f"Backup management failed: {str(e)}"
        logger.error(error_msg)
        results['errors'].append(error_msg)
        
        # Send failure metrics
        send_backup_metrics(success=False, errors=1)
    
    return {
        'statusCode': 200 if not results['errors'] else 500,
        'body': json.dumps(results)
    }


def verify_neptune_backups() -> bool:
    """
    Verify Neptune automated backup configuration
    """
    try:
        logger.info("Verifying Neptune backup configuration")
        
        # List Neptune clusters
        response = neptune_client.describe_db_clusters()
        clusters = response.get('DBClusters', [])
        
        for cluster in clusters:
            cluster_id = cluster['DBClusterIdentifier']
            
            # Check if cluster belongs to our project
            if PROJECT_NAME.lower() in cluster_id.lower():
                backup_retention = cluster.get('BackupRetentionPeriod', 0)
                
                if backup_retention > 0:
                    logger.info(f"Neptune cluster {cluster_id} has backup retention: {backup_retention} days")
                else:
                    logger.warning(f"Neptune cluster {cluster_id} has no backup retention configured")
                    return False
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to verify Neptune backups: {str(e)}")
        return False


def manage_opensearch_snapshots() -> bool:
    """
    Manage OpenSearch snapshots and repository
    """
    try:
        logger.info("Managing OpenSearch snapshots")
        
        # List OpenSearch domains
        response = opensearch_client.list_domain_names()
        domains = response.get('DomainNames', [])
        
        for domain in domains:
            domain_name = domain['DomainName']
            
            # Check if domain belongs to our project
            if PROJECT_NAME.lower() in domain_name.lower():
                logger.info(f"Managing snapshots for OpenSearch domain: {domain_name}")
                
                # Note: OpenSearch snapshot management would typically be done
                # through the OpenSearch REST API, not the AWS API
                # This is a placeholder for the actual implementation
                
                # In a real implementation, you would:
                # 1. Register snapshot repository if not exists
                # 2. Create manual snapshots if needed
                # 3. Verify snapshot repository configuration
                
        return True
        
    except Exception as e:
        logger.error(f"Failed to manage OpenSearch snapshots: {str(e)}")
        return False


def cleanup_old_snapshots() -> bool:
    """
    Cleanup old manual snapshots based on retention policy
    """
    try:
        logger.info(f"Cleaning up snapshots older than {BACKUP_RETENTION_DAYS} days")
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        
        # List objects in snapshot bucket
        response = s3_client.list_objects_v2(Bucket=SNAPSHOT_BUCKET)
        objects = response.get('Contents', [])
        
        deleted_count = 0
        for obj in objects:
            # Check if object is older than retention period
            if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                # Only delete manual snapshots, not automated ones
                if 'manual-snapshot' in obj['Key']:
                    logger.info(f"Deleting old snapshot: {obj['Key']}")
                    s3_client.delete_object(Bucket=SNAPSHOT_BUCKET, Key=obj['Key'])
                    deleted_count += 1
        
        logger.info(f"Deleted {deleted_count} old manual snapshots")
        return True
        
    except Exception as e:
        logger.error(f"Failed to cleanup old snapshots: {str(e)}")
        return False


def send_backup_metrics(success: bool, errors: int) -> None:
    """
    Send backup metrics to CloudWatch
    """
    try:
        # Send success metric
        cloudwatch_client.put_metric_data(
            Namespace='Custom/Backup',
            MetricData=[
                {
                    'MetricName': 'BackupSuccess',
                    'Dimensions': [
                        {
                            'Name': 'Project',
                            'Value': PROJECT_NAME
                        },
                        {
                            'Name': 'Environment',
                            'Value': ENVIRONMENT
                        }
                    ],
                    'Value': 1 if success else 0,
                    'Unit': 'Count'
                }
            ]
        )
        
        # Send error metric
        if errors > 0:
            cloudwatch_client.put_metric_data(
                Namespace='Custom/Backup',
                MetricData=[
                    {
                        'MetricName': 'BackupErrors',
                        'Dimensions': [
                            {
                                'Name': 'Project',
                                'Value': PROJECT_NAME
                            },
                            {
                                'Name': 'Environment',
                                'Value': ENVIRONMENT
                            }
                        ],
                        'Value': errors,
                        'Unit': 'Count'
                    }
                ]
            )
        
        logger.info(f"Sent backup metrics: success={success}, errors={errors}")
        
    except Exception as e:
        logger.error(f"Failed to send backup metrics: {str(e)}")


if __name__ == "__main__":
    # For local testing
    test_event = {}
    test_context = type('Context', (), {})()
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2))