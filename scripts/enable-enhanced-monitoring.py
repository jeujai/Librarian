#!/usr/bin/env python3
"""
Enhanced monitoring enablement script.
Enables enhanced monitoring and alerting for post-deployment period.
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnhancedMonitoring:
    """Manages enhanced monitoring configuration."""
    
    def __init__(self, environment: str, aws_region: str = 'us-east-1'):
        self.environment = environment
        self.aws_region = aws_region
        
        # AWS clients
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=aws_region)
        self.logs_client = boto3.client('logs', region_name=aws_region)
        self.sns_client = boto3.client('sns', region_name=aws_region)
        self.ssm_client = boto3.client('ssm', region_name=aws_region)
        
        # Resource naming
        self.namespace = f'MultimodalLibrarian/{environment.title()}'
        self.alarm_prefix = f'multimodal-librarian-{environment}'
        
    def create_enhanced_alarms(self, duration_hours: int = 24) -> List[str]:
        """Create enhanced CloudWatch alarms for monitoring period."""
        logger.info(f"Creating enhanced alarms for {duration_hours} hours...")
        
        created_alarms = []
        
        # Get SNS topic for notifications
        sns_topic_arn = self.get_notification_topic()
        
        # Enhanced alarm configurations
        enhanced_alarms = [
            {
                'name': f'{self.alarm_prefix}-high-error-rate-enhanced',
                'description': 'Enhanced monitoring: High error rate detected',
                'metric_name': 'HTTPCode_Target_5XX_Count',
                'namespace': 'AWS/ApplicationELB',
                'statistic': 'Sum',
                'period': 60,  # 1 minute
                'evaluation_periods': 2,
                'threshold': 5,  # More sensitive than normal
                'comparison_operator': 'GreaterThanThreshold',
                'dimensions': [
                    {
                        'Name': 'LoadBalancer',
                        'Value': f'app/{self.alarm_prefix}/*'
                    }
                ]
            },
            {
                'name': f'{self.alarm_prefix}-high-response-time-enhanced',
                'description': 'Enhanced monitoring: High response time detected',
                'metric_name': 'TargetResponseTime',
                'namespace': 'AWS/ApplicationELB',
                'statistic': 'Average',
                'period': 60,
                'evaluation_periods': 3,
                'threshold': 2.0,  # More sensitive
                'comparison_operator': 'GreaterThanThreshold',
                'dimensions': [
                    {
                        'Name': 'LoadBalancer',
                        'Value': f'app/{self.alarm_prefix}/*'
                    }
                ]
            },
            {
                'name': f'{self.alarm_prefix}-cpu-utilization-enhanced',
                'description': 'Enhanced monitoring: High CPU utilization',
                'metric_name': 'CPUUtilization',
                'namespace': 'AWS/ECS',
                'statistic': 'Average',
                'period': 60,
                'evaluation_periods': 2,
                'threshold': 70.0,  # Lower threshold
                'comparison_operator': 'GreaterThanThreshold',
                'dimensions': [
                    {
                        'Name': 'ServiceName',
                        'Value': self.alarm_prefix
                    },
                    {
                        'Name': 'ClusterName',
                        'Value': self.alarm_prefix
                    }
                ]
            },
            {
                'name': f'{self.alarm_prefix}-memory-utilization-enhanced',
                'description': 'Enhanced monitoring: High memory utilization',
                'metric_name': 'MemoryUtilization',
                'namespace': 'AWS/ECS',
                'statistic': 'Average',
                'period': 60,
                'evaluation_periods': 2,
                'threshold': 80.0,  # Lower threshold
                'comparison_operator': 'GreaterThanThreshold',
                'dimensions': [
                    {
                        'Name': 'ServiceName',
                        'Value': self.alarm_prefix
                    },
                    {
                        'Name': 'ClusterName',
                        'Value': self.alarm_prefix
                    }
                ]
            },
            {
                'name': f'{self.alarm_prefix}-task-count-low-enhanced',
                'description': 'Enhanced monitoring: Low running task count',
                'metric_name': 'RunningTaskCount',
                'namespace': 'AWS/ECS',
                'statistic': 'Average',
                'period': 60,
                'evaluation_periods': 1,
                'threshold': 1,  # Alert if less than 2 tasks
                'comparison_operator': 'LessThanThreshold',
                'dimensions': [
                    {
                        'Name': 'ServiceName',
                        'Value': self.alarm_prefix
                    },
                    {
                        'Name': 'ClusterName',
                        'Value': self.alarm_prefix
                    }
                ]
            },
            {
                'name': f'{self.alarm_prefix}-database-connections-enhanced',
                'description': 'Enhanced monitoring: High database connection count',
                'metric_name': 'DatabaseConnections',
                'namespace': 'AWS/Neptune',
                'statistic': 'Average',
                'period': 300,  # 5 minutes
                'evaluation_periods': 2,
                'threshold': 80,  # Lower threshold
                'comparison_operator': 'GreaterThanThreshold',
                'dimensions': [
                    {
                        'Name': 'DBClusterIdentifier',
                        'Value': f'{self.alarm_prefix}-neptune'
                    }
                ]
            }
        ]
        
        # Create alarms
        for alarm_config in enhanced_alarms:
            try:
                self.cloudwatch_client.put_metric_alarm(
                    AlarmName=alarm_config['name'],
                    AlarmDescription=alarm_config['description'],
                    ActionsEnabled=True,
                    AlarmActions=[sns_topic_arn] if sns_topic_arn else [],
                    MetricName=alarm_config['metric_name'],
                    Namespace=alarm_config['namespace'],
                    Statistic=alarm_config['statistic'],
                    Dimensions=alarm_config['dimensions'],
                    Period=alarm_config['period'],
                    EvaluationPeriods=alarm_config['evaluation_periods'],
                    Threshold=alarm_config['threshold'],
                    ComparisonOperator=alarm_config['comparison_operator'],
                    TreatMissingData='notBreaching'
                )
                
                created_alarms.append(alarm_config['name'])
                logger.info(f"Created enhanced alarm: {alarm_config['name']}")
                
            except ClientError as e:
                logger.error(f"Failed to create alarm {alarm_config['name']}: {str(e)}")
        
        return created_alarms
    
    def create_custom_metrics(self) -> List[str]:
        """Create custom application metrics for enhanced monitoring."""
        logger.info("Setting up custom metrics...")
        
        custom_metrics = []
        
        # Custom metric configurations
        metrics_config = [
            {
                'name': 'DeploymentHealth',
                'description': 'Overall deployment health score',
                'unit': 'Percent'
            },
            {
                'name': 'APIResponseSuccess',
                'description': 'API response success rate',
                'unit': 'Percent'
            },
            {
                'name': 'DatabaseQueryLatency',
                'description': 'Database query latency',
                'unit': 'Milliseconds'
            },
            {
                'name': 'ActiveUserSessions',
                'description': 'Number of active user sessions',
                'unit': 'Count'
            }
        ]
        
        # Put initial metric data points
        for metric in metrics_config:
            try:
                # Put a baseline metric
                self.cloudwatch_client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=[
                        {
                            'MetricName': metric['name'],
                            'Value': 100.0 if metric['unit'] == 'Percent' else 0.0,
                            'Unit': metric['unit'],
                            'Timestamp': datetime.utcnow()
                        }
                    ]
                )
                
                custom_metrics.append(metric['name'])
                logger.info(f"Initialized custom metric: {metric['name']}")
                
            except ClientError as e:
                logger.error(f"Failed to create custom metric {metric['name']}: {str(e)}")
        
        return custom_metrics
    
    def enable_detailed_logging(self) -> bool:
        """Enable detailed logging for enhanced monitoring period."""
        logger.info("Enabling detailed logging...")
        
        try:
            # Update log retention for enhanced monitoring
            log_groups = [
                f'/ecs/{self.alarm_prefix}',
                f'/aws/lambda/{self.alarm_prefix}',
                f'/aws/apigateway/{self.alarm_prefix}'
            ]
            
            for log_group in log_groups:
                try:
                    # Set shorter retention for detailed logs during monitoring
                    self.logs_client.put_retention_policy(
                        logGroupName=log_group,
                        retentionInDays=7  # Keep detailed logs for 7 days
                    )
                    
                    logger.info(f"Updated retention for log group: {log_group}")
                    
                except ClientError as e:
                    if e.response['Error']['Code'] != 'ResourceNotFoundException':
                        logger.warning(f"Could not update log group {log_group}: {str(e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable detailed logging: {str(e)}")
            return False
    
    def create_enhanced_dashboard(self) -> str:
        """Create enhanced monitoring dashboard."""
        logger.info("Creating enhanced monitoring dashboard...")
        
        dashboard_name = f'{self.alarm_prefix}-enhanced-monitoring'
        
        # Dashboard configuration
        dashboard_body = {
            "widgets": [
                {
                    "type": "metric",
                    "x": 0,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", f"app/{self.alarm_prefix}"],
                            [".", "HTTPCode_Target_2XX_Count", ".", "."],
                            [".", "HTTPCode_Target_4XX_Count", ".", "."],
                            [".", "HTTPCode_Target_5XX_Count", ".", "."]
                        ],
                        "period": 60,
                        "stat": "Sum",
                        "region": self.aws_region,
                        "title": "Request Metrics (Enhanced)"
                    }
                },
                {
                    "type": "metric",
                    "x": 12,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", f"app/{self.alarm_prefix}"]
                        ],
                        "period": 60,
                        "stat": "Average",
                        "region": self.aws_region,
                        "title": "Response Time (Enhanced)"
                    }
                },
                {
                    "type": "metric",
                    "x": 0,
                    "y": 6,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["AWS/ECS", "CPUUtilization", "ServiceName", self.alarm_prefix, "ClusterName", self.alarm_prefix],
                            [".", "MemoryUtilization", ".", ".", ".", "."]
                        ],
                        "period": 60,
                        "stat": "Average",
                        "region": self.aws_region,
                        "title": "ECS Resource Utilization (Enhanced)"
                    }
                },
                {
                    "type": "metric",
                    "x": 12,
                    "y": 6,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            [self.namespace, "DeploymentHealth"],
                            [".", "APIResponseSuccess"]
                        ],
                        "period": 300,
                        "stat": "Average",
                        "region": self.aws_region,
                        "title": "Custom Application Metrics"
                    }
                },
                {
                    "type": "log",
                    "x": 0,
                    "y": 12,
                    "width": 24,
                    "height": 6,
                    "properties": {
                        "query": f"SOURCE '/ecs/{self.alarm_prefix}'\n| fields @timestamp, @message\n| filter @message like /ERROR/\n| sort @timestamp desc\n| limit 100",
                        "region": self.aws_region,
                        "title": "Recent Errors (Enhanced Monitoring)"
                    }
                }
            ]
        }
        
        try:
            self.cloudwatch_client.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"Created enhanced dashboard: {dashboard_name}")
            return dashboard_name
            
        except ClientError as e:
            logger.error(f"Failed to create enhanced dashboard: {str(e)}")
            return ""
    
    def get_notification_topic(self) -> str:
        """Get or create SNS topic for enhanced monitoring notifications."""
        topic_name = f'{self.alarm_prefix}-enhanced-monitoring'
        
        try:
            # Try to find existing topic
            topics_response = self.sns_client.list_topics()
            
            for topic in topics_response['Topics']:
                if topic_name in topic['TopicArn']:
                    return topic['TopicArn']
            
            # Create new topic if not found
            create_response = self.sns_client.create_topic(Name=topic_name)
            topic_arn = create_response['TopicArn']
            
            # Set topic attributes for enhanced monitoring
            self.sns_client.set_topic_attributes(
                TopicArn=topic_arn,
                AttributeName='DisplayName',
                AttributeValue=f'Enhanced Monitoring - {self.environment.title()}'
            )
            
            logger.info(f"Created SNS topic for enhanced monitoring: {topic_arn}")
            return topic_arn
            
        except ClientError as e:
            logger.error(f"Failed to get/create SNS topic: {str(e)}")
            return ""
    
    def schedule_monitoring_disable(self, duration_hours: int):
        """Schedule automatic disabling of enhanced monitoring."""
        try:
            # Store the end time in Parameter Store
            end_time = datetime.utcnow() + timedelta(hours=duration_hours)
            
            self.ssm_client.put_parameter(
                Name=f'/multimodal-librarian/{self.environment}/enhanced-monitoring-end',
                Value=end_time.isoformat(),
                Type='String',
                Overwrite=True,
                Description=f'Enhanced monitoring end time for {self.environment}'
            )
            
            logger.info(f"Scheduled enhanced monitoring to end at: {end_time.isoformat()}")
            
        except ClientError as e:
            logger.error(f"Failed to schedule monitoring disable: {str(e)}")
    
    def disable_enhanced_monitoring(self) -> bool:
        """Disable enhanced monitoring and clean up resources."""
        logger.info("Disabling enhanced monitoring...")
        
        try:
            # Delete enhanced alarms
            alarm_names = []
            
            # Get all alarms with enhanced prefix
            paginator = self.cloudwatch_client.get_paginator('describe_alarms')
            
            for page in paginator.paginate(AlarmNamePrefix=f'{self.alarm_prefix}-'):
                for alarm in page['MetricAlarms']:
                    if 'enhanced' in alarm['AlarmName']:
                        alarm_names.append(alarm['AlarmName'])
            
            if alarm_names:
                # Delete in batches of 100 (AWS limit)
                for i in range(0, len(alarm_names), 100):
                    batch = alarm_names[i:i+100]
                    self.cloudwatch_client.delete_alarms(AlarmNames=batch)
                    logger.info(f"Deleted {len(batch)} enhanced alarms")
            
            # Delete enhanced dashboard
            dashboard_name = f'{self.alarm_prefix}-enhanced-monitoring'
            try:
                self.cloudwatch_client.delete_dashboards(
                    DashboardNames=[dashboard_name]
                )
                logger.info(f"Deleted enhanced dashboard: {dashboard_name}")
            except ClientError:
                pass  # Dashboard might not exist
            
            # Reset log retention to normal
            log_groups = [
                f'/ecs/{self.alarm_prefix}',
                f'/aws/lambda/{self.alarm_prefix}',
                f'/aws/apigateway/{self.alarm_prefix}'
            ]
            
            for log_group in log_groups:
                try:
                    self.logs_client.put_retention_policy(
                        logGroupName=log_group,
                        retentionInDays=30  # Normal retention
                    )
                except ClientError:
                    pass  # Log group might not exist
            
            # Clean up parameter
            try:
                self.ssm_client.delete_parameter(
                    Name=f'/multimodal-librarian/{self.environment}/enhanced-monitoring-end'
                )
            except ClientError:
                pass
            
            logger.info("Enhanced monitoring disabled successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable enhanced monitoring: {str(e)}")
            return False


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Manage enhanced monitoring')
    parser.add_argument('--environment', required=True,
                       choices=['staging', 'production'],
                       help='Target environment')
    parser.add_argument('--action', required=True,
                       choices=['enable', 'disable', 'status'],
                       help='Action to perform')
    parser.add_argument('--duration', default='24h',
                       help='Duration for enhanced monitoring (e.g., "24h", "2d")')
    parser.add_argument('--aws-region', default='us-east-1',
                       help='AWS region (default: us-east-1)')
    
    args = parser.parse_args()
    
    # Parse duration
    duration_str = args.duration.lower()
    if duration_str.endswith('h'):
        duration_hours = int(duration_str[:-1])
    elif duration_str.endswith('d'):
        duration_hours = int(duration_str[:-1]) * 24
    else:
        duration_hours = int(duration_str)  # Assume hours
    
    monitoring = EnhancedMonitoring(args.environment, args.aws_region)
    
    try:
        if args.action == 'enable':
            logger.info(f"Enabling enhanced monitoring for {duration_hours} hours...")
            
            # Create enhanced alarms
            alarms = monitoring.create_enhanced_alarms(duration_hours)
            
            # Create custom metrics
            metrics = monitoring.create_custom_metrics()
            
            # Enable detailed logging
            monitoring.enable_detailed_logging()
            
            # Create enhanced dashboard
            dashboard = monitoring.create_enhanced_dashboard()
            
            # Schedule automatic disable
            monitoring.schedule_monitoring_disable(duration_hours)
            
            logger.info(f"Enhanced monitoring enabled:")
            logger.info(f"  Created {len(alarms)} enhanced alarms")
            logger.info(f"  Initialized {len(metrics)} custom metrics")
            logger.info(f"  Dashboard: {dashboard}")
            logger.info(f"  Duration: {duration_hours} hours")
            
            return 0
            
        elif args.action == 'disable':
            logger.info("Disabling enhanced monitoring...")
            
            success = monitoring.disable_enhanced_monitoring()
            
            if success:
                logger.info("Enhanced monitoring disabled successfully")
                return 0
            else:
                logger.error("Failed to disable enhanced monitoring")
                return 1
                
        elif args.action == 'status':
            logger.info("Checking enhanced monitoring status...")
            
            # Check if enhanced monitoring is active
            try:
                response = monitoring.ssm_client.get_parameter(
                    Name=f'/multimodal-librarian/{args.environment}/enhanced-monitoring-end'
                )
                
                end_time = datetime.fromisoformat(response['Parameter']['Value'])
                current_time = datetime.utcnow()
                
                if current_time < end_time:
                    remaining = end_time - current_time
                    logger.info(f"Enhanced monitoring is ACTIVE")
                    logger.info(f"Time remaining: {remaining}")
                else:
                    logger.info("Enhanced monitoring has EXPIRED")
                    
            except ClientError:
                logger.info("Enhanced monitoring is NOT ACTIVE")
            
            return 0
            
    except Exception as e:
        logger.error(f"Enhanced monitoring operation failed: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())