#!/usr/bin/env python3
"""
Disaster Recovery Service

Provides disaster recovery testing, validation, and monitoring capabilities.
Integrates with the application to provide continuous DR readiness assessment.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import boto3
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class RecoveryTimeObjective:
    """Recovery Time Objective configuration."""
    component: str
    target_seconds: int
    current_seconds: Optional[int] = None
    status: str = "unknown"  # unknown, met, exceeded
    last_tested: Optional[datetime] = None


@dataclass
class RecoveryPointObjective:
    """Recovery Point Objective configuration."""
    component: str
    target_seconds: int
    current_seconds: Optional[int] = None
    status: str = "unknown"  # unknown, met, exceeded
    last_backup: Optional[datetime] = None


@dataclass
class BackupStatus:
    """Backup status information."""
    component: str
    backup_type: str
    last_backup: Optional[datetime] = None
    backup_size: Optional[int] = None
    status: str = "unknown"  # unknown, success, failed, in_progress
    retention_days: int = 7
    next_backup: Optional[datetime] = None


@dataclass
class DisasterRecoveryStatus:
    """Overall disaster recovery status."""
    overall_status: str = "unknown"  # ready, warning, critical, unknown
    last_test: Optional[datetime] = None
    next_test: Optional[datetime] = None
    rto_objectives: List[RecoveryTimeObjective] = None
    rpo_objectives: List[RecoveryPointObjective] = None
    backup_statuses: List[BackupStatus] = None
    issues: List[str] = None
    recommendations: List[str] = None
    
    def __post_init__(self):
        if self.rto_objectives is None:
            self.rto_objectives = []
        if self.rpo_objectives is None:
            self.rpo_objectives = []
        if self.backup_statuses is None:
            self.backup_statuses = []
        if self.issues is None:
            self.issues = []
        if self.recommendations is None:
            self.recommendations = []


class DisasterRecoveryService:
    """
    Disaster Recovery Service
    
    Provides comprehensive disaster recovery testing, validation,
    and monitoring capabilities.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # AWS clients
        self.aws_session = boto3.Session()
        self.rds_client = self.aws_session.client('rds')
        self.s3_client = self.aws_session.client('s3')
        self.lambda_client = self.aws_session.client('lambda')
        self.ecs_client = self.aws_session.client('ecs')
        self.cloudwatch_client = self.aws_session.client('cloudwatch')
        self.secrets_client = self.aws_session.client('secretsmanager')
        
        # Configuration
        self.project_name = self.config.get('project_name', 'multimodal-librarian')
        self.environment = self.config.get('environment', 'production')
        
        # Default RTO/RPO targets (in seconds)
        self.default_rto_targets = {
            'infrastructure': 2 * 3600,  # 2 hours
            'database': 1 * 3600,        # 1 hour
            'application': 30 * 60,      # 30 minutes
            'validation': 30 * 60        # 30 minutes
        }
        
        self.default_rpo_targets = {
            'database': 1 * 3600,        # 1 hour
            'files': 4 * 3600,           # 4 hours
            'configuration': 24 * 3600   # 24 hours
        }
        
        # Test scheduling
        self.test_interval_days = self.config.get('test_interval_days', 30)
        self.backup_check_interval_hours = self.config.get('backup_check_interval_hours', 6)
        
        # Current status
        self._current_status = DisasterRecoveryStatus()
        self._last_status_update = None
    
    async def get_disaster_recovery_status(self, force_refresh: bool = False) -> DisasterRecoveryStatus:
        """
        Get current disaster recovery status.
        
        Args:
            force_refresh: Force refresh of status data
            
        Returns:
            Current disaster recovery status
        """
        # Check if we need to refresh status
        if (force_refresh or 
            self._last_status_update is None or 
            datetime.now() - self._last_status_update > timedelta(hours=1)):
            
            await self._refresh_disaster_recovery_status()
        
        return self._current_status
    
    async def _refresh_disaster_recovery_status(self) -> None:
        """Refresh disaster recovery status from AWS resources."""
        logger.info("Refreshing disaster recovery status")
        
        try:
            # Get backup statuses
            backup_statuses = await self._get_backup_statuses()
            
            # Get RTO objectives
            rto_objectives = await self._get_rto_objectives()
            
            # Get RPO objectives
            rpo_objectives = await self._get_rpo_objectives()
            
            # Analyze overall status
            overall_status, issues, recommendations = await self._analyze_overall_status(
                backup_statuses, rto_objectives, rpo_objectives
            )
            
            # Update current status
            self._current_status = DisasterRecoveryStatus(
                overall_status=overall_status,
                last_test=await self._get_last_test_date(),
                next_test=await self._get_next_test_date(),
                rto_objectives=rto_objectives,
                rpo_objectives=rpo_objectives,
                backup_statuses=backup_statuses,
                issues=issues,
                recommendations=recommendations
            )
            
            self._last_status_update = datetime.now()
            
            logger.info(f"Disaster recovery status updated: {overall_status}")
        
        except Exception as e:
            logger.error(f"Failed to refresh disaster recovery status: {str(e)}")
            self._current_status.overall_status = "unknown"
            self._current_status.issues.append(f"Status refresh failed: {str(e)}")
    
    async def _get_backup_statuses(self) -> List[BackupStatus]:
        """Get backup statuses for all components."""
        backup_statuses = []
        
        try:
            # RDS backup status
            rds_status = await self._get_rds_backup_status()
            backup_statuses.extend(rds_status)
            
            # S3 backup status
            s3_status = await self._get_s3_backup_status()
            backup_statuses.extend(s3_status)
            
            # Lambda backup function status
            lambda_status = await self._get_lambda_backup_status()
            backup_statuses.extend(lambda_status)
        
        except Exception as e:
            logger.error(f"Failed to get backup statuses: {str(e)}")
        
        return backup_statuses
    
    async def _get_rds_backup_status(self) -> List[BackupStatus]:
        """Get RDS backup status."""
        statuses = []
        
        try:
            # Get RDS instances
            response = self.rds_client.describe_db_instances()
            
            for instance in response['DBInstances']:
                db_id = instance['DBInstanceIdentifier']
                
                if self.project_name in db_id:
                    # Get backup retention
                    retention_days = instance.get('BackupRetentionPeriod', 0)
                    
                    # Get latest snapshot
                    snapshots = self.rds_client.describe_db_snapshots(
                        DBInstanceIdentifier=db_id,
                        SnapshotType='automated',
                        MaxRecords=1
                    )
                    
                    last_backup = None
                    backup_size = None
                    status = "unknown"
                    
                    if snapshots['DBSnapshots']:
                        latest_snapshot = snapshots['DBSnapshots'][0]
                        last_backup = latest_snapshot['SnapshotCreateTime']
                        backup_size = latest_snapshot.get('AllocatedStorage', 0) * 1024 * 1024 * 1024  # GB to bytes
                        status = "success" if latest_snapshot['Status'] == 'available' else "failed"
                    
                    statuses.append(BackupStatus(
                        component=f"rds-{db_id}",
                        backup_type="automated",
                        last_backup=last_backup,
                        backup_size=backup_size,
                        status=status,
                        retention_days=retention_days
                    ))
        
        except Exception as e:
            logger.error(f"Failed to get RDS backup status: {str(e)}")
        
        return statuses
    
    async def _get_s3_backup_status(self) -> List[BackupStatus]:
        """Get S3 backup status."""
        statuses = []
        
        try:
            # List backup buckets
            response = self.s3_client.list_buckets()
            
            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                
                if 'backup' in bucket_name.lower() and self.project_name in bucket_name:
                    # Get bucket objects
                    try:
                        objects_response = self.s3_client.list_objects_v2(
                            Bucket=bucket_name,
                            MaxKeys=1
                        )
                        
                        last_backup = None
                        backup_size = 0
                        status = "unknown"
                        
                        if objects_response.get('Contents'):
                            # Get most recent object
                            latest_object = max(
                                objects_response['Contents'],
                                key=lambda x: x['LastModified']
                            )
                            last_backup = latest_object['LastModified']
                            
                            # Get total bucket size
                            all_objects = self.s3_client.list_objects_v2(Bucket=bucket_name)
                            backup_size = sum(obj['Size'] for obj in all_objects.get('Contents', []))
                            status = "success"
                        
                        statuses.append(BackupStatus(
                            component=f"s3-{bucket_name}",
                            backup_type="manual",
                            last_backup=last_backup,
                            backup_size=backup_size,
                            status=status,
                            retention_days=30  # Default S3 lifecycle
                        ))
                    
                    except Exception as e:
                        logger.error(f"Failed to check S3 bucket {bucket_name}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Failed to get S3 backup status: {str(e)}")
        
        return statuses
    
    async def _get_lambda_backup_status(self) -> List[BackupStatus]:
        """Get Lambda backup function status."""
        statuses = []
        
        try:
            # List Lambda functions
            response = self.lambda_client.list_functions()
            
            for function in response['Functions']:
                func_name = function['FunctionName']
                
                if 'backup' in func_name.lower() and self.project_name in func_name:
                    # Get function metrics from CloudWatch
                    try:
                        metrics_response = self.cloudwatch_client.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Invocations',
                            Dimensions=[
                                {
                                    'Name': 'FunctionName',
                                    'Value': func_name
                                }
                            ],
                            StartTime=datetime.now() - timedelta(days=1),
                            EndTime=datetime.now(),
                            Period=3600,
                            Statistics=['Sum']
                        )
                        
                        last_backup = None
                        status = "unknown"
                        
                        if metrics_response['Datapoints']:
                            # Get most recent invocation
                            latest_datapoint = max(
                                metrics_response['Datapoints'],
                                key=lambda x: x['Timestamp']
                            )
                            last_backup = latest_datapoint['Timestamp']
                            status = "success" if latest_datapoint['Sum'] > 0 else "failed"
                        
                        statuses.append(BackupStatus(
                            component=f"lambda-{func_name}",
                            backup_type="scheduled",
                            last_backup=last_backup,
                            status=status,
                            retention_days=7  # Default retention
                        ))
                    
                    except Exception as e:
                        logger.error(f"Failed to get metrics for Lambda function {func_name}: {str(e)}")
        
        except Exception as e:
            logger.error(f"Failed to get Lambda backup status: {str(e)}")
        
        return statuses
    
    async def _get_rto_objectives(self) -> List[RecoveryTimeObjective]:
        """Get Recovery Time Objectives."""
        objectives = []
        
        for component, target_seconds in self.default_rto_targets.items():
            # Get current RTO from historical data or estimates
            current_seconds = await self._estimate_recovery_time(component)
            
            status = "unknown"
            if current_seconds is not None:
                status = "met" if current_seconds <= target_seconds else "exceeded"
            
            objectives.append(RecoveryTimeObjective(
                component=component,
                target_seconds=target_seconds,
                current_seconds=current_seconds,
                status=status,
                last_tested=await self._get_last_test_date()
            ))
        
        return objectives
    
    async def _get_rpo_objectives(self) -> List[RecoveryPointObjective]:
        """Get Recovery Point Objectives."""
        objectives = []
        
        for component, target_seconds in self.default_rpo_targets.items():
            # Get current RPO from backup ages
            current_seconds = await self._get_backup_age(component)
            
            status = "unknown"
            if current_seconds is not None:
                status = "met" if current_seconds <= target_seconds else "exceeded"
            
            objectives.append(RecoveryPointObjective(
                component=component,
                target_seconds=target_seconds,
                current_seconds=current_seconds,
                status=status,
                last_backup=await self._get_last_backup_date(component)
            ))
        
        return objectives
    
    async def _estimate_recovery_time(self, component: str) -> Optional[int]:
        """Estimate recovery time for a component."""
        # This would typically use historical data or predefined estimates
        estimates = {
            'infrastructure': 2 * 3600,  # 2 hours
            'database': 45 * 60,         # 45 minutes
            'application': 20 * 60,      # 20 minutes
            'validation': 15 * 60        # 15 minutes
        }
        
        return estimates.get(component)
    
    async def _get_backup_age(self, component: str) -> Optional[int]:
        """Get age of latest backup for a component."""
        try:
            if component == 'database':
                # Get RDS backup age
                response = self.rds_client.describe_db_instances()
                
                for instance in response['DBInstances']:
                    if self.project_name in instance['DBInstanceIdentifier']:
                        snapshots = self.rds_client.describe_db_snapshots(
                            DBInstanceIdentifier=instance['DBInstanceIdentifier'],
                            SnapshotType='automated',
                            MaxRecords=1
                        )
                        
                        if snapshots['DBSnapshots']:
                            latest_snapshot = snapshots['DBSnapshots'][0]
                            backup_age = (
                                datetime.now() - latest_snapshot['SnapshotCreateTime'].replace(tzinfo=None)
                            ).total_seconds()
                            return int(backup_age)
            
            elif component == 'files':
                # Get S3 backup age
                response = self.s3_client.list_buckets()
                
                for bucket in response['Buckets']:
                    if 'backup' in bucket['Name'].lower() and self.project_name in bucket['Name']:
                        objects = self.s3_client.list_objects_v2(
                            Bucket=bucket['Name'],
                            MaxKeys=1
                        )
                        
                        if objects.get('Contents'):
                            latest_object = max(
                                objects['Contents'],
                                key=lambda x: x['LastModified']
                            )
                            backup_age = (
                                datetime.now() - latest_object['LastModified'].replace(tzinfo=None)
                            ).total_seconds()
                            return int(backup_age)
        
        except Exception as e:
            logger.error(f"Failed to get backup age for {component}: {str(e)}")
        
        return None
    
    async def _get_last_backup_date(self, component: str) -> Optional[datetime]:
        """Get date of last backup for a component."""
        backup_age = await self._get_backup_age(component)
        if backup_age is not None:
            return datetime.now() - timedelta(seconds=backup_age)
        return None
    
    async def _get_last_test_date(self) -> Optional[datetime]:
        """Get date of last disaster recovery test."""
        # This would typically be stored in a database or configuration
        # For now, return a simulated date
        return datetime.now() - timedelta(days=15)
    
    async def _get_next_test_date(self) -> Optional[datetime]:
        """Get date of next scheduled disaster recovery test."""
        last_test = await self._get_last_test_date()
        if last_test:
            return last_test + timedelta(days=self.test_interval_days)
        return None
    
    async def _analyze_overall_status(
        self,
        backup_statuses: List[BackupStatus],
        rto_objectives: List[RecoveryTimeObjective],
        rpo_objectives: List[RecoveryPointObjective]
    ) -> Tuple[str, List[str], List[str]]:
        """Analyze overall disaster recovery status."""
        issues = []
        recommendations = []
        
        # Check backup statuses
        failed_backups = [b for b in backup_statuses if b.status == "failed"]
        old_backups = [
            b for b in backup_statuses 
            if b.last_backup and (datetime.now() - b.last_backup.replace(tzinfo=None)).days > 1
        ]
        
        if failed_backups:
            issues.append(f"{len(failed_backups)} backup(s) have failed")
            recommendations.append("Investigate and fix failed backup procedures")
        
        if old_backups:
            issues.append(f"{len(old_backups)} backup(s) are more than 1 day old")
            recommendations.append("Check backup scheduling and execution")
        
        # Check RTO objectives
        exceeded_rto = [r for r in rto_objectives if r.status == "exceeded"]
        if exceeded_rto:
            issues.append(f"{len(exceeded_rto)} RTO objective(s) exceeded")
            recommendations.append("Optimize recovery procedures to meet RTO targets")
        
        # Check RPO objectives
        exceeded_rpo = [r for r in rpo_objectives if r.status == "exceeded"]
        if exceeded_rpo:
            issues.append(f"{len(exceeded_rpo)} RPO objective(s) exceeded")
            recommendations.append("Increase backup frequency to meet RPO targets")
        
        # Check test schedule
        last_test = await self._get_last_test_date()
        if last_test and (datetime.now() - last_test).days > self.test_interval_days:
            issues.append("Disaster recovery test is overdue")
            recommendations.append("Schedule and execute disaster recovery test")
        
        # Determine overall status
        if not issues:
            overall_status = "ready"
        elif len(issues) <= 2 and not failed_backups and not exceeded_rto:
            overall_status = "warning"
        else:
            overall_status = "critical"
        
        return overall_status, issues, recommendations
    
    async def run_backup_validation(self) -> Dict[str, Any]:
        """Run backup validation tests."""
        logger.info("Running backup validation")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'backup_tests': {},
            'issues': [],
            'success': True
        }
        
        try:
            # Test RDS backups
            rds_results = await self._validate_rds_backups()
            results['backup_tests']['rds'] = rds_results
            
            # Test S3 backups
            s3_results = await self._validate_s3_backups()
            results['backup_tests']['s3'] = s3_results
            
            # Test Lambda backup functions
            lambda_results = await self._validate_lambda_backups()
            results['backup_tests']['lambda'] = lambda_results
            
            # Analyze results
            all_tests = [rds_results, s3_results, lambda_results]
            failed_tests = [t for t in all_tests if not t.get('success', False)]
            
            if failed_tests:
                results['success'] = False
                results['issues'].extend([
                    issue for test in failed_tests 
                    for issue in test.get('issues', [])
                ])
        
        except Exception as e:
            logger.error(f"Backup validation failed: {str(e)}")
            results['success'] = False
            results['issues'].append(f"Backup validation error: {str(e)}")
        
        return results
    
    async def _validate_rds_backups(self) -> Dict[str, Any]:
        """Validate RDS backup procedures."""
        results = {
            'success': True,
            'issues': [],
            'backup_count': 0,
            'retention_days': 0
        }
        
        try:
            response = self.rds_client.describe_db_instances()
            
            for instance in response['DBInstances']:
                db_id = instance['DBInstanceIdentifier']
                
                if self.project_name in db_id:
                    # Check backup retention
                    retention = instance.get('BackupRetentionPeriod', 0)
                    results['retention_days'] = max(results['retention_days'], retention)
                    
                    if retention == 0:
                        results['success'] = False
                        results['issues'].append(f"RDS instance {db_id} has no backup retention")
                    
                    # Check for recent snapshots
                    snapshots = self.rds_client.describe_db_snapshots(
                        DBInstanceIdentifier=db_id,
                        SnapshotType='automated'
                    )
                    
                    recent_snapshots = [
                        s for s in snapshots['DBSnapshots']
                        if (datetime.now() - s['SnapshotCreateTime'].replace(tzinfo=None)).days < 1
                    ]
                    
                    results['backup_count'] += len(recent_snapshots)
                    
                    if not recent_snapshots:
                        results['success'] = False
                        results['issues'].append(f"RDS instance {db_id} has no recent backups")
        
        except Exception as e:
            results['success'] = False
            results['issues'].append(f"RDS backup validation failed: {str(e)}")
        
        return results
    
    async def _validate_s3_backups(self) -> Dict[str, Any]:
        """Validate S3 backup procedures."""
        results = {
            'success': True,
            'issues': [],
            'bucket_count': 0,
            'total_size': 0
        }
        
        try:
            response = self.s3_client.list_buckets()
            
            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                
                if 'backup' in bucket_name.lower() and self.project_name in bucket_name:
                    results['bucket_count'] += 1
                    
                    try:
                        # Check bucket contents
                        objects = self.s3_client.list_objects_v2(Bucket=bucket_name)
                        
                        if not objects.get('Contents'):
                            results['success'] = False
                            results['issues'].append(f"Backup bucket {bucket_name} is empty")
                        else:
                            # Calculate total size
                            bucket_size = sum(obj['Size'] for obj in objects['Contents'])
                            results['total_size'] += bucket_size
                    
                    except Exception as e:
                        results['success'] = False
                        results['issues'].append(f"Failed to access backup bucket {bucket_name}: {str(e)}")
            
            if results['bucket_count'] == 0:
                results['success'] = False
                results['issues'].append("No backup buckets found")
        
        except Exception as e:
            results['success'] = False
            results['issues'].append(f"S3 backup validation failed: {str(e)}")
        
        return results
    
    async def _validate_lambda_backups(self) -> Dict[str, Any]:
        """Validate Lambda backup functions."""
        results = {
            'success': True,
            'issues': [],
            'function_count': 0,
            'recent_executions': 0
        }
        
        try:
            response = self.lambda_client.list_functions()
            
            for function in response['Functions']:
                func_name = function['FunctionName']
                
                if 'backup' in func_name.lower() and self.project_name in func_name:
                    results['function_count'] += 1
                    
                    try:
                        # Check recent executions
                        metrics = self.cloudwatch_client.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Invocations',
                            Dimensions=[{'Name': 'FunctionName', 'Value': func_name}],
                            StartTime=datetime.now() - timedelta(days=1),
                            EndTime=datetime.now(),
                            Period=3600,
                            Statistics=['Sum']
                        )
                        
                        if metrics['Datapoints']:
                            total_invocations = sum(dp['Sum'] for dp in metrics['Datapoints'])
                            results['recent_executions'] += int(total_invocations)
                            
                            if total_invocations == 0:
                                results['success'] = False
                                results['issues'].append(f"Lambda function {func_name} has not executed recently")
                    
                    except Exception as e:
                        results['success'] = False
                        results['issues'].append(f"Failed to check Lambda function {func_name}: {str(e)}")
            
            if results['function_count'] == 0:
                results['success'] = False
                results['issues'].append("No backup Lambda functions found")
        
        except Exception as e:
            results['success'] = False
            results['issues'].append(f"Lambda backup validation failed: {str(e)}")
        
        return results
    
    async def generate_recovery_report(self) -> Dict[str, Any]:
        """Generate comprehensive disaster recovery report."""
        logger.info("Generating disaster recovery report")
        
        # Get current status
        status = await self.get_disaster_recovery_status(force_refresh=True)
        
        # Run backup validation
        backup_validation = await self.run_backup_validation()
        
        # Generate report
        report = {
            'report_timestamp': datetime.now().isoformat(),
            'overall_status': status.overall_status,
            'summary': {
                'rto_objectives_met': sum(1 for rto in status.rto_objectives if rto.status == "met"),
                'rto_objectives_total': len(status.rto_objectives),
                'rpo_objectives_met': sum(1 for rpo in status.rpo_objectives if rpo.status == "met"),
                'rpo_objectives_total': len(status.rpo_objectives),
                'successful_backups': sum(1 for backup in status.backup_statuses if backup.status == "success"),
                'total_backups': len(status.backup_statuses),
                'issues_count': len(status.issues),
                'recommendations_count': len(status.recommendations)
            },
            'detailed_status': asdict(status),
            'backup_validation': backup_validation,
            'next_actions': self._generate_next_actions(status, backup_validation)
        }
        
        return report
    
    def _generate_next_actions(
        self,
        status: DisasterRecoveryStatus,
        backup_validation: Dict[str, Any]
    ) -> List[str]:
        """Generate next actions based on current status."""
        actions = []
        
        # High priority actions
        if status.overall_status == "critical":
            actions.append("URGENT: Address critical disaster recovery issues immediately")
        
        if not backup_validation.get('success', False):
            actions.append("Fix backup validation failures")
        
        # RTO/RPO actions
        exceeded_rto = [r for r in status.rto_objectives if r.status == "exceeded"]
        if exceeded_rto:
            actions.append(f"Optimize recovery procedures for {len(exceeded_rto)} component(s)")
        
        exceeded_rpo = [r for r in status.rpo_objectives if r.status == "exceeded"]
        if exceeded_rpo:
            actions.append(f"Increase backup frequency for {len(exceeded_rpo)} component(s)")
        
        # Test scheduling
        if status.next_test and status.next_test < datetime.now():
            actions.append("Schedule overdue disaster recovery test")
        
        # General recommendations
        actions.extend(status.recommendations)
        
        return actions


# API integration functions
async def get_disaster_recovery_status() -> Dict[str, Any]:
    """Get disaster recovery status for API endpoints."""
    service = DisasterRecoveryService()
    status = await service.get_disaster_recovery_status()
    return asdict(status)


async def run_disaster_recovery_validation() -> Dict[str, Any]:
    """Run disaster recovery validation for API endpoints."""
    service = DisasterRecoveryService()
    return await service.run_backup_validation()


async def generate_disaster_recovery_report() -> Dict[str, Any]:
    """Generate disaster recovery report for API endpoints."""
    service = DisasterRecoveryService()
    return await service.generate_recovery_report()