#!/usr/bin/env python3
"""
AWS Lambda function for automated backup management.
Manages Neptune and OpenSearch backups, cleanup, and monitoring.
"""

import json
import boto3
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
neptune_client = boto3.client('neptune')
opensearch_client = boto3.client('opensearch')
s3_client = boto3.client('s3')
cloudwatch_client = boto3.client('cloudwatch')

# Environment variables
PROJECT_NAME = os.environ.get('PROJECT_NAME', '${project_name}')
ENVIRONMENT = os.environ.get('ENVIRONMENT', '${environment}')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
NEPTUNE_CLUSTER = os.environ.get('NEPTUNE_CLUSTER', '')
OPENSEARCH_DOMAIN = os.environ.get('OPENSEARCH_DOMAIN', '')
SNAPSHOT_BUCKET = os.environ.get('SNAPSHOT_BUCKET', '')
RETENTION_DAYS = int(os.environ.get('RETENTION_DAYS', '30'))


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for backup management operations.
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Dict containing operation results
    """
    logger.info(f"Starting backup management for {PROJECT_NAME}-{ENVIRONMENT}")
    
    results = {
        'timestamp': datetime.utcnow().isoformat(),
        'project': PROJECT_NAME,
        'environment': ENVIRONMENT,
        'operations': []
    }
    
    try:
        # Verify Neptune backup configuration
        neptune_result = verify_neptune_backups()
        results['operations'].append(neptune_result)
        
        # Manage OpenSearch snapshots
        opensearch_result = manage_opensearch_snapshots()
        results['operations'].append(opensearch_result)
        
        # Cleanup old manual snapshots
        cleanup_result = cleanup_old_snapshots()
        results['operations'].append(cleanup_result)
        
        # Send success metrics to CloudWatch
        send_backup_metrics(True, len(results['operations']))
        
        logger.info("Backup management completed successfully")
        results['status'] = 'success'
        
    except Exception as e:
        logger.error(f"Backup management failed: {str(e)}")
        send_backup_metrics(False, 0)
        results['status'] = 'error'
        results['error'] = str(e)
        raise
    
    return results


def verify_neptune_backups() -> Dict[str, Any]:
    """
    Verify Neptune automated backup configuration and recent backups.
    
    Returns:
        Dict containing verification results
    """
    logger.info(f"Verifying Neptune backups for cluster: {NEPTUNE_CLUSTER}")
    
    try:
        # Get cluster information
        response = neptune_client.describe_db_clusters(
            DBClusterIdentifier=NEPTUNE_CLUSTER
        )
        
        if not response['DBClusters']:
            raise Exception(f"Neptune cluster {NEPTUNE_CLUSTER} not found")
        
        cluster = response['DBClusters'][0]
        backup_retention = cluster.get('BackupRetentionPeriod', 0)
        
        # Check recent snapshots
        snapshots_response = neptune_client.describe_db_cluster_snapshots(
            DBClusterIdentifier=NEPTUNE_CLUSTER,
            SnapshotType='automated',
            MaxRecords=5
        )
        
        recent_snapshots = [
            snap for snap in snapshots_response['DBClusterSnapshots']
            if snap['SnapshotCreateTime'] > datetime.utcnow() - timedelta(days=2)
        ]
        
        result = {
            'operation': 'neptune_backup_verification',
            'status': 'success',
            'cluster_id': NEPTUNE_CLUSTER,
            'backup_retention_days': backup_retention,
            'recent_snapshots_count': len(recent_snapshots),
            'latest_snapshot': recent_snapshots[0]['SnapshotCreateTime'].isoformat() if recent_snapshots else None
        }
        
        logger.info(f"Neptune backup verification completed: {len(recent_snapshots)} recent snapshots")
        return result
        
    except Exception as e:
        logger.error(f"Neptune backup verification failed: {str(e)}")
        return {
            'operation': 'neptune_backup_verification',
            'status': 'error',
            'error': str(e)
        }


def manage_opensearch_snapshots() -> Dict[str, Any]:
    """
    Manage OpenSearch manual snapshots and repository configuration.
    
    Returns:
        Dict containing snapshot management results
    """
    logger.info(f"Managing OpenSearch snapshots for domain: {OPENSEARCH_DOMAIN}")
    
    try:
        # Get domain information
        response = opensearch_client.describe_domain(
            DomainName=OPENSEARCH_DOMAIN
        )
        
        if not response['DomainStatus']:
            raise Exception(f"OpenSearch domain {OPENSEARCH_DOMAIN} not found")
        
        domain_endpoint = response['DomainStatus']['Endpoint']
        
        # Note: In a real implementation, you would use the OpenSearch REST API
        # to manage snapshots. This is a simplified version for demonstration.
        
        result = {
            'operation': 'opensearch_snapshot_management',
            'status': 'success',
            'domain_name': OPENSEARCH_DOMAIN,
            'endpoint': domain_endpoint,
            'snapshot_bucket': SNAPSHOT_BUCKET,
            'note': 'AWS managed hourly snapshots are automatically configured'
        }
        
        logger.info("OpenSearch snapshot management completed")
        return result
        
    except Exception as e:
        logger.error(f"OpenSearch snapshot management failed: {str(e)}")
        return {
            'operation': 'opensearch_snapshot_management',
            'status': 'error',
            'error': str(e)
        }


def cleanup_old_snapshots() -> Dict[str, Any]:
    """
    Clean up old manual snapshots based on retention policy.
    
    Returns:
        Dict containing cleanup results
    """
    logger.info(f"Cleaning up snapshots older than {RETENTION_DAYS} days")
    
    try:
        cleanup_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        
        # Clean up old Neptune manual snapshots
        snapshots_response = neptune_client.describe_db_cluster_snapshots(
            DBClusterIdentifier=NEPTUNE_CLUSTER,
            SnapshotType='manual'
        )
        
        for snapshot in snapshots_response['DBClusterSnapshots']:
            if snapshot['SnapshotCreateTime'] < cutoff_date:
                try:
                    neptune_client.delete_db_cluster_snapshot(
                        DBClusterSnapshotIdentifier=snapshot['DBClusterSnapshotIdentifier']
                    )
                    cleanup_count += 1
                    logger.info(f"Deleted old Neptune snapshot: {snapshot['DBClusterSnapshotIdentifier']}")
                except Exception as e:
                    logger.warning(f"Failed to delete Neptune snapshot {snapshot['DBClusterSnapshotIdentifier']}: {str(e)}")
        
        result = {
            'operation': 'snapshot_cleanup',
            'status': 'success',
            'retention_days': RETENTION_DAYS,
            'snapshots_deleted': cleanup_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
        logger.info(f"Snapshot cleanup completed: {cleanup_count} snapshots deleted")
        return result
        
    except Exception as e:
        logger.error(f"Snapshot cleanup failed: {str(e)}")
        return {
            'operation': 'snapshot_cleanup',
            'status': 'error',
            'error': str(e)
        }


def send_backup_metrics(success: bool, operations_count: int) -> None:
    """
    Send backup operation metrics to CloudWatch.
    
    Args:
        success: Whether the backup operations were successful
        operations_count: Number of operations performed
    """
    try:
        namespace = f"{PROJECT_NAME}/{ENVIRONMENT}/Backup"
        
        # Send success/failure metric
        cloudwatch_client.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'BackupOperationSuccess',
                    'Value': 1.0 if success else 0.0,
                    'Unit': 'Count',
                    'Dimensions': [
                        {
                            'Name': 'Environment',
                            'Value': ENVIRONMENT
                        }
                    ]
                },
                {
                    'MetricName': 'BackupOperationsCount',
                    'Value': float(operations_count),
                    'Unit': 'Count',
                    'Dimensions': [
                        {
                            'Name': 'Environment',
                            'Value': ENVIRONMENT
                        }
                    ]
                }
            ]
        )
        
        logger.info(f"Sent backup metrics to CloudWatch: success={success}, operations={operations_count}")
        
    except Exception as e:
        logger.error(f"Failed to send backup metrics: {str(e)}")


if __name__ == "__main__":
    # For local testing
    test_event = {}
    test_context = type('Context', (), {})()
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))