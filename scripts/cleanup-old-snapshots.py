#!/usr/bin/env python3
"""
Cleanup old snapshots script.
Removes old Neptune and OpenSearch snapshots based on retention policy.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SnapshotCleaner:
    """Manages cleanup of old database snapshots."""
    
    def __init__(self, aws_region: str = 'us-east-1'):
        self.aws_region = aws_region
        
        # AWS clients
        self.neptune_client = boto3.client('neptune', region_name=aws_region)
        self.opensearch_client = boto3.client('opensearch', region_name=aws_region)
        self.s3_client = boto3.client('s3', region_name=aws_region)
    
    def get_neptune_snapshots(self, cluster_identifier: str = None) -> List[Dict]:
        """Get list of Neptune cluster snapshots."""
        try:
            params = {
                'SnapshotType': 'manual',  # Only manual snapshots
                'MaxRecords': 100
            }
            
            if cluster_identifier:
                params['DBClusterIdentifier'] = cluster_identifier
            
            response = self.neptune_client.describe_db_cluster_snapshots(**params)
            
            snapshots = []
            for snapshot in response['DBClusterSnapshots']:
                snapshots.append({
                    'identifier': snapshot['DBClusterSnapshotIdentifier'],
                    'cluster_id': snapshot['DBClusterIdentifier'],
                    'created_time': snapshot['SnapshotCreateTime'],
                    'status': snapshot['Status'],
                    'size': snapshot.get('AllocatedStorage', 0),
                    'type': 'neptune'
                })
            
            # Sort by creation time (oldest first)
            snapshots.sort(key=lambda x: x['created_time'])
            
            return snapshots
            
        except ClientError as e:
            logger.error(f"Failed to get Neptune snapshots: {str(e)}")
            return []
    
    def get_opensearch_snapshots(self, domain_name: str = None) -> List[Dict]:
        """Get list of OpenSearch snapshots from S3."""
        try:
            # OpenSearch snapshots are stored in S3
            # We need to list them from the snapshot repository
            
            snapshots = []
            
            if domain_name:
                # Get domain configuration to find snapshot bucket
                domain_response = self.opensearch_client.describe_domain(
                    DomainName=domain_name
                )
                
                # Extract snapshot configuration if available
                # This is a simplified version - actual implementation would
                # need to query the OpenSearch cluster directly for snapshot info
                
                # For now, we'll simulate getting snapshots from S3
                bucket_name = f"opensearch-snapshots-{domain_name}"
                
                try:
                    objects_response = self.s3_client.list_objects_v2(
                        Bucket=bucket_name,
                        Prefix='snapshots/'
                    )
                    
                    for obj in objects_response.get('Contents', []):
                        # Parse snapshot information from S3 object
                        key_parts = obj['Key'].split('/')
                        if len(key_parts) >= 3:
                            snapshot_name = key_parts[1]
                            
                            snapshots.append({
                                'identifier': snapshot_name,
                                'domain_name': domain_name,
                                'created_time': obj['LastModified'],
                                'status': 'SUCCESS',  # Assume successful if in S3
                                'size': obj['Size'],
                                'type': 'opensearch',
                                's3_key': obj['Key']
                            })
                
                except ClientError as e:
                    if e.response['Error']['Code'] != 'NoSuchBucket':
                        logger.warning(f"Could not access snapshot bucket {bucket_name}: {str(e)}")
            
            # Sort by creation time (oldest first)
            snapshots.sort(key=lambda x: x['created_time'])
            
            return snapshots
            
        except ClientError as e:
            logger.error(f"Failed to get OpenSearch snapshots: {str(e)}")
            return []
    
    def delete_neptune_snapshot(self, snapshot_identifier: str) -> bool:
        """Delete a Neptune cluster snapshot."""
        try:
            self.neptune_client.delete_db_cluster_snapshot(
                DBClusterSnapshotIdentifier=snapshot_identifier
            )
            
            logger.info(f"Deleted Neptune snapshot: {snapshot_identifier}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete Neptune snapshot {snapshot_identifier}: {str(e)}")
            return False
    
    def delete_opensearch_snapshot(self, snapshot_info: Dict) -> bool:
        """Delete an OpenSearch snapshot from S3."""
        try:
            # Extract bucket and key from snapshot info
            if 's3_key' in snapshot_info:
                bucket_name = f"opensearch-snapshots-{snapshot_info['domain_name']}"
                
                self.s3_client.delete_object(
                    Bucket=bucket_name,
                    Key=snapshot_info['s3_key']
                )
                
                logger.info(f"Deleted OpenSearch snapshot: {snapshot_info['identifier']}")
                return True
            else:
                logger.warning(f"No S3 key found for snapshot: {snapshot_info['identifier']}")
                return False
                
        except ClientError as e:
            logger.error(f"Failed to delete OpenSearch snapshot {snapshot_info['identifier']}: {str(e)}")
            return False
    
    def cleanup_snapshots_by_age(self, snapshots: List[Dict], 
                                retention_days: int, dry_run: bool = False) -> Dict:
        """Clean up snapshots older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        old_snapshots = [
            snapshot for snapshot in snapshots
            if snapshot['created_time'].replace(tzinfo=None) < cutoff_date
        ]
        
        results = {
            'total_snapshots': len(snapshots),
            'old_snapshots': len(old_snapshots),
            'deleted_snapshots': 0,
            'failed_deletions': 0,
            'deleted_list': [],
            'failed_list': []
        }
        
        if not old_snapshots:
            logger.info(f"No snapshots older than {retention_days} days found")
            return results
        
        logger.info(f"Found {len(old_snapshots)} snapshots older than {retention_days} days")
        
        for snapshot in old_snapshots:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete {snapshot['type']} snapshot: "
                          f"{snapshot['identifier']} "
                          f"(created: {snapshot['created_time'].strftime('%Y-%m-%d %H:%M:%S')})")
                results['deleted_snapshots'] += 1
                results['deleted_list'].append(snapshot['identifier'])
            else:
                logger.info(f"Deleting {snapshot['type']} snapshot: "
                          f"{snapshot['identifier']} "
                          f"(created: {snapshot['created_time'].strftime('%Y-%m-%d %H:%M:%S')})")
                
                if snapshot['type'] == 'neptune':
                    success = self.delete_neptune_snapshot(snapshot['identifier'])
                elif snapshot['type'] == 'opensearch':
                    success = self.delete_opensearch_snapshot(snapshot)
                else:
                    logger.warning(f"Unknown snapshot type: {snapshot['type']}")
                    success = False
                
                if success:
                    results['deleted_snapshots'] += 1
                    results['deleted_list'].append(snapshot['identifier'])
                else:
                    results['failed_deletions'] += 1
                    results['failed_list'].append(snapshot['identifier'])
                
                # Small delay to avoid rate limiting
                time.sleep(1)
        
        return results
    
    def cleanup_snapshots_by_count(self, snapshots: List[Dict], 
                                  max_snapshots: int, dry_run: bool = False) -> Dict:
        """Clean up snapshots to keep only the most recent N snapshots."""
        if len(snapshots) <= max_snapshots:
            logger.info(f"Only {len(snapshots)} snapshots found, "
                       f"keeping all (max: {max_snapshots})")
            return {
                'total_snapshots': len(snapshots),
                'old_snapshots': 0,
                'deleted_snapshots': 0,
                'failed_deletions': 0,
                'deleted_list': [],
                'failed_list': []
            }
        
        # Sort by creation time (newest first) and keep the most recent
        snapshots_sorted = sorted(snapshots, key=lambda x: x['created_time'], reverse=True)
        snapshots_to_keep = snapshots_sorted[:max_snapshots]
        snapshots_to_delete = snapshots_sorted[max_snapshots:]
        
        results = {
            'total_snapshots': len(snapshots),
            'old_snapshots': len(snapshots_to_delete),
            'deleted_snapshots': 0,
            'failed_deletions': 0,
            'deleted_list': [],
            'failed_list': []
        }
        
        logger.info(f"Keeping {len(snapshots_to_keep)} most recent snapshots, "
                   f"deleting {len(snapshots_to_delete)} older snapshots")
        
        for snapshot in snapshots_to_delete:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete {snapshot['type']} snapshot: "
                          f"{snapshot['identifier']} "
                          f"(created: {snapshot['created_time'].strftime('%Y-%m-%d %H:%M:%S')})")
                results['deleted_snapshots'] += 1
                results['deleted_list'].append(snapshot['identifier'])
            else:
                logger.info(f"Deleting {snapshot['type']} snapshot: "
                          f"{snapshot['identifier']} "
                          f"(created: {snapshot['created_time'].strftime('%Y-%m-%d %H:%M:%S')})")
                
                if snapshot['type'] == 'neptune':
                    success = self.delete_neptune_snapshot(snapshot['identifier'])
                elif snapshot['type'] == 'opensearch':
                    success = self.delete_opensearch_snapshot(snapshot)
                else:
                    logger.warning(f"Unknown snapshot type: {snapshot['type']}")
                    success = False
                
                if success:
                    results['deleted_snapshots'] += 1
                    results['deleted_list'].append(snapshot['identifier'])
                else:
                    results['failed_deletions'] += 1
                    results['failed_list'].append(snapshot['identifier'])
                
                # Small delay to avoid rate limiting
                time.sleep(1)
        
        return results


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Cleanup old database snapshots')
    parser.add_argument('--retention-days', type=int, default=7,
                       help='Retention period in days (default: 7)')
    parser.add_argument('--max-snapshots', type=int,
                       help='Maximum number of snapshots to keep (overrides retention-days)')
    parser.add_argument('--neptune-cluster',
                       help='Neptune cluster identifier to clean up')
    parser.add_argument('--opensearch-domain',
                       help='OpenSearch domain name to clean up')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--aws-region', default='us-east-1',
                       help='AWS region (default: us-east-1)')
    
    args = parser.parse_args()
    
    logger.info("Starting snapshot cleanup...")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No snapshots will actually be deleted")
    
    cleaner = SnapshotCleaner(args.aws_region)
    
    total_results = {
        'total_snapshots': 0,
        'deleted_snapshots': 0,
        'failed_deletions': 0
    }
    
    try:
        # Clean up Neptune snapshots
        if args.neptune_cluster:
            logger.info(f"Cleaning up Neptune snapshots for cluster: {args.neptune_cluster}")
            
            neptune_snapshots = cleaner.get_neptune_snapshots(args.neptune_cluster)
            
            if neptune_snapshots:
                if args.max_snapshots:
                    results = cleaner.cleanup_snapshots_by_count(
                        neptune_snapshots, args.max_snapshots, args.dry_run
                    )
                else:
                    results = cleaner.cleanup_snapshots_by_age(
                        neptune_snapshots, args.retention_days, args.dry_run
                    )
                
                total_results['total_snapshots'] += results['total_snapshots']
                total_results['deleted_snapshots'] += results['deleted_snapshots']
                total_results['failed_deletions'] += results['failed_deletions']
                
                logger.info(f"Neptune cleanup: {results['deleted_snapshots']} deleted, "
                          f"{results['failed_deletions']} failed")
        
        # Clean up OpenSearch snapshots
        if args.opensearch_domain:
            logger.info(f"Cleaning up OpenSearch snapshots for domain: {args.opensearch_domain}")
            
            opensearch_snapshots = cleaner.get_opensearch_snapshots(args.opensearch_domain)
            
            if opensearch_snapshots:
                if args.max_snapshots:
                    results = cleaner.cleanup_snapshots_by_count(
                        opensearch_snapshots, args.max_snapshots, args.dry_run
                    )
                else:
                    results = cleaner.cleanup_snapshots_by_age(
                        opensearch_snapshots, args.retention_days, args.dry_run
                    )
                
                total_results['total_snapshots'] += results['total_snapshots']
                total_results['deleted_snapshots'] += results['deleted_snapshots']
                total_results['failed_deletions'] += results['failed_deletions']
                
                logger.info(f"OpenSearch cleanup: {results['deleted_snapshots']} deleted, "
                          f"{results['failed_deletions']} failed")
        
        # If no specific resources specified, clean up all
        if not args.neptune_cluster and not args.opensearch_domain:
            logger.info("No specific resources specified, cleaning up all snapshots...")
            
            # Get all Neptune snapshots
            all_neptune_snapshots = cleaner.get_neptune_snapshots()
            if all_neptune_snapshots:
                if args.max_snapshots:
                    results = cleaner.cleanup_snapshots_by_count(
                        all_neptune_snapshots, args.max_snapshots, args.dry_run
                    )
                else:
                    results = cleaner.cleanup_snapshots_by_age(
                        all_neptune_snapshots, args.retention_days, args.dry_run
                    )
                
                total_results['total_snapshots'] += results['total_snapshots']
                total_results['deleted_snapshots'] += results['deleted_snapshots']
                total_results['failed_deletions'] += results['failed_deletions']
        
        # Summary
        logger.info(f"\nCleanup Summary:")
        logger.info(f"  Total snapshots processed: {total_results['total_snapshots']}")
        logger.info(f"  Snapshots deleted: {total_results['deleted_snapshots']}")
        logger.info(f"  Failed deletions: {total_results['failed_deletions']}")
        
        if args.dry_run:
            logger.info("  (DRY RUN - No actual deletions performed)")
        
        # Return appropriate exit code
        if total_results['failed_deletions'] > 0:
            logger.warning("Some snapshot deletions failed")
            return 1
        else:
            logger.info("Snapshot cleanup completed successfully")
            return 0
            
    except Exception as e:
        logger.error(f"Snapshot cleanup failed: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())