#!/usr/bin/env python3
"""
AWS Lambda function for automated resource cleanup.
Cleans up old CloudWatch log streams, unused EBS snapshots, and other resources
to optimize costs.
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
logs_client = boto3.client('logs')
ec2_client = boto3.client('ec2')
cloudwatch_client = boto3.client('cloudwatch')

# Environment variables
PROJECT_NAME = os.environ.get('PROJECT_NAME', '${project_name}')
ENVIRONMENT = os.environ.get('ENVIRONMENT', '${environment}')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Cleanup configuration
LOG_STREAM_RETENTION_DAYS = 30
SNAPSHOT_RETENTION_DAYS = 7


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for resource cleanup operations.
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Dict containing cleanup results
    """
    logger.info(f"Starting resource cleanup for {PROJECT_NAME}-{ENVIRONMENT}")
    
    results = {
        'timestamp': datetime.utcnow().isoformat(),
        'project': PROJECT_NAME,
        'environment': ENVIRONMENT,
        'cleanup_operations': []
    }
    
    try:
        # Clean up old CloudWatch log streams
        log_cleanup_result = cleanup_old_log_streams()
        results['cleanup_operations'].append(log_cleanup_result)
        
        # Clean up unused EBS snapshots
        snapshot_cleanup_result = cleanup_unused_snapshots()
        results['cleanup_operations'].append(snapshot_cleanup_result)
        
        # Send success metrics to CloudWatch
        total_cleaned = sum(op.get('items_cleaned', 0) for op in results['cleanup_operations'])
        send_cleanup_metrics(True, total_cleaned)
        
        logger.info("Resource cleanup completed successfully")
        results['status'] = 'success'
        results['total_items_cleaned'] = total_cleaned
        
    except Exception as e:
        logger.error(f"Resource cleanup failed: {str(e)}")
        send_cleanup_metrics(False, 0)
        results['status'] = 'error'
        results['error'] = str(e)
        raise
    
    return results


def cleanup_old_log_streams() -> Dict[str, Any]:
    """
    Clean up old CloudWatch log streams to reduce storage costs.
    
    Returns:
        Dict containing log cleanup results
    """
    logger.info(f"Cleaning up log streams older than {LOG_STREAM_RETENTION_DAYS} days")
    
    try:
        cleanup_count = 0
        cutoff_timestamp = int((datetime.utcnow() - timedelta(days=LOG_STREAM_RETENTION_DAYS)).timestamp() * 1000)
        
        # Get log groups for the project
        log_groups_response = logs_client.describe_log_groups(
            logGroupNamePrefix=f"/aws/ecs/{PROJECT_NAME}-{ENVIRONMENT}"
        )
        
        for log_group in log_groups_response['logGroups']:
            log_group_name = log_group['logGroupName']
            
            try:
                # Get log streams for this group
                streams_response = logs_client.describe_log_streams(
                    logGroupName=log_group_name,
                    orderBy='LastEventTime',
                    descending=False
                )
                
                for stream in streams_response['logStreams']:
                    # Check if stream is old and has no recent activity
                    last_event_time = stream.get('lastEventTime', 0)
                    if last_event_time < cutoff_timestamp and last_event_time > 0:
                        try:
                            logs_client.delete_log_stream(
                                logGroupName=log_group_name,
                                logStreamName=stream['logStreamName']
                            )
                            cleanup_count += 1
                            logger.info(f"Deleted old log stream: {stream['logStreamName']}")
                        except Exception as e:
                            logger.warning(f"Failed to delete log stream {stream['logStreamName']}: {str(e)}")
                            
            except Exception as e:
                logger.warning(f"Failed to process log group {log_group_name}: {str(e)}")
        
        result = {
            'operation': 'log_stream_cleanup',
            'status': 'success',
            'retention_days': LOG_STREAM_RETENTION_DAYS,
            'items_cleaned': cleanup_count,
            'cutoff_timestamp': cutoff_timestamp
        }
        
        logger.info(f"Log stream cleanup completed: {cleanup_count} streams deleted")
        return result
        
    except Exception as e:
        logger.error(f"Log stream cleanup failed: {str(e)}")
        return {
            'operation': 'log_stream_cleanup',
            'status': 'error',
            'error': str(e),
            'items_cleaned': 0
        }


def cleanup_unused_snapshots() -> Dict[str, Any]:
    """
    Clean up unused EBS snapshots to reduce storage costs.
    Only deletes snapshots that are not associated with AMIs.
    
    Returns:
        Dict containing snapshot cleanup results
    """
    logger.info(f"Cleaning up unused snapshots older than {SNAPSHOT_RETENTION_DAYS} days")
    
    try:
        cleanup_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=SNAPSHOT_RETENTION_DAYS)
        
        # Get all snapshots owned by this account
        snapshots_response = ec2_client.describe_snapshots(
            OwnerIds=['self'],
            Filters=[
                {
                    'Name': 'tag:Project',
                    'Values': [PROJECT_NAME]
                }
            ]
        )
        
        # Get all AMIs to check which snapshots are in use
        images_response = ec2_client.describe_images(
            Owners=['self']
        )
        
        # Create set of snapshot IDs that are used by AMIs
        used_snapshot_ids = set()
        for image in images_response['Images']:
            for block_device in image.get('BlockDeviceMappings', []):
                if 'Ebs' in block_device and 'SnapshotId' in block_device['Ebs']:
                    used_snapshot_ids.add(block_device['Ebs']['SnapshotId'])
        
        # Check each snapshot for cleanup eligibility
        for snapshot in snapshots_response['Snapshots']:
            snapshot_id = snapshot['SnapshotId']
            start_time = snapshot['StartTime'].replace(tzinfo=None)
            
            # Skip if snapshot is too recent or is used by an AMI
            if start_time > cutoff_date or snapshot_id in used_snapshot_ids:
                continue
            
            # Additional safety check: ensure snapshot is not tagged as protected
            tags = {tag['Key']: tag['Value'] for tag in snapshot.get('Tags', [])}
            if tags.get('Protected', '').lower() == 'true':
                continue
            
            try:
                ec2_client.delete_snapshot(SnapshotId=snapshot_id)
                cleanup_count += 1
                logger.info(f"Deleted unused snapshot: {snapshot_id}")
            except Exception as e:
                logger.warning(f"Failed to delete snapshot {snapshot_id}: {str(e)}")
        
        result = {
            'operation': 'snapshot_cleanup',
            'status': 'success',
            'retention_days': SNAPSHOT_RETENTION_DAYS,
            'items_cleaned': cleanup_count,
            'cutoff_date': cutoff_date.isoformat(),
            'total_snapshots_checked': len(snapshots_response['Snapshots']),
            'snapshots_protected_by_ami': len(used_snapshot_ids)
        }
        
        logger.info(f"Snapshot cleanup completed: {cleanup_count} snapshots deleted")
        return result
        
    except Exception as e:
        logger.error(f"Snapshot cleanup failed: {str(e)}")
        return {
            'operation': 'snapshot_cleanup',
            'status': 'error',
            'error': str(e),
            'items_cleaned': 0
        }


def send_cleanup_metrics(success: bool, items_cleaned: int) -> None:
    """
    Send cleanup operation metrics to CloudWatch.
    
    Args:
        success: Whether the cleanup operations were successful
        items_cleaned: Number of items cleaned up
    """
    try:
        namespace = f"{PROJECT_NAME}/{ENVIRONMENT}/ResourceCleanup"
        
        # Send success/failure metric
        cloudwatch_client.put_metric_data(
            Namespace=na