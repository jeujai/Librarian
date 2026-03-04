#!/usr/bin/env python3
"""
Configure Startup Monitoring and Alerting

This script configures CloudWatch monitoring and alerting for the application
startup optimization system. It sets up SNS subscriptions, validates alarm
configurations, and enables monitoring integration.

Usage:
    python scripts/configure-startup-monitoring.py --environment prod --email alerts@example.com
"""

import argparse
import json
import logging
import sys
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StartupMonitoringConfigurator:
    """Configure startup monitoring and alerting in AWS."""
    
    def __init__(self, environment: str, region: str = "us-east-1"):
        """Initialize the configurator."""
        self.environment = environment
        self.region = region
        self.name_prefix = f"multimodal-librarian-{environment}"
        
        # AWS clients
        self.sns_client = boto3.client('sns', region_name=region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region)
        self.logs_client = boto3.client('logs', region_name=region)
        
        logger.info(f"Initialized configurator for environment: {environment}, region: {region}")
    
    def configure_sns_subscriptions(self, email_addresses: List[str], 
                                   phone_numbers: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Configure SNS topic subscriptions for startup alerts.
        
        Args:
            email_addresses: List of email addresses to subscribe
            phone_numbers: Optional list of phone numbers for SMS alerts
            
        Returns:
            Dictionary mapping topic names to subscription ARNs
        """
        logger.info("Configuring SNS subscriptions for startup alerts")
        
        subscriptions = {}
        
        # Find startup alerts topic
        try:
            topics = self.sns_client.list_topics()
            startup_topic_arn = None
            
            for topic in topics.get('Topics', []):
                if f"{self.name_prefix}-startup-alerts" in topic['TopicArn']:
                    startup_topic_arn = topic['TopicArn']
                    break
            
            if not startup_topic_arn:
                logger.error(f"Startup alerts topic not found for {self.name_prefix}")
                return subscriptions
            
            logger.info(f"Found startup alerts topic: {startup_topic_arn}")
            
            # Subscribe email addresses
            for email in email_addresses:
                try:
                    response = self.sns_client.subscribe(
                        TopicArn=startup_topic_arn,
                        Protocol='email',
                        Endpoint=email,
                        ReturnSubscriptionArn=True
                    )
                    subscriptions[f"email_{email}"] = response['SubscriptionArn']
                    logger.info(f"Subscribed email: {email}")
                except ClientError as e:
                    logger.error(f"Failed to subscribe email {email}: {e}")
            
            # Subscribe phone numbers for SMS (optional)
            if phone_numbers:
                for phone in phone_numbers:
                    try:
                        response = self.sns_client.subscribe(
                            TopicArn=startup_topic_arn,
                            Protocol='sms',
                            Endpoint=phone,
                            ReturnSubscriptionArn=True
                        )
                        subscriptions[f"sms_{phone}"] = response['SubscriptionArn']
                        logger.info(f"Subscribed SMS: {phone}")
                    except ClientError as e:
                        logger.error(f"Failed to subscribe SMS {phone}: {e}")
            
            return subscriptions
            
        except ClientError as e:
            logger.error(f"Error configuring SNS subscriptions: {e}")
            return subscriptions
    
    def validate_alarms(self) -> Dict[str, bool]:
        """
        Validate that all startup monitoring alarms are configured correctly.
        
        Returns:
            Dictionary mapping alarm names to validation status
        """
        logger.info("Validating startup monitoring alarms")
        
        validation_results = {}
        
        # Expected alarms
        expected_alarms = [
            f"{self.name_prefix}-minimal-phase-timeout",
            f"{self.name_prefix}-essential-phase-timeout",
            f"{self.name_prefix}-full-phase-timeout",
            f"{self.name_prefix}-model-loading-failures",
            f"{self.name_prefix}-model-loading-slow",
            f"{self.name_prefix}-user-wait-time-high",
            f"{self.name_prefix}-user-wait-time-p95-high",
            f"{self.name_prefix}-high-fallback-usage",
            f"{self.name_prefix}-low-cache-hit-rate",
            f"{self.name_prefix}-health-check-failures",
            f"{self.name_prefix}-startup-failure-composite"
        ]
        
        try:
            # Get all alarms
            paginator = self.cloudwatch_client.get_paginator('describe_alarms')
            
            existing_alarms = set()
            for page in paginator.paginate():
                for alarm in page.get('MetricAlarms', []) + page.get('CompositeAlarms', []):
                    existing_alarms.add(alarm['AlarmName'])
            
            # Validate each expected alarm
            for alarm_name in expected_alarms:
                exists = alarm_name in existing_alarms
                validation_results[alarm_name] = exists
                
                if exists:
                    logger.info(f"✓ Alarm configured: {alarm_name}")
                else:
                    logger.warning(f"✗ Alarm missing: {alarm_name}")
            
            # Summary
            configured_count = sum(validation_results.values())
            total_count = len(expected_alarms)
            logger.info(f"Alarm validation: {configured_count}/{total_count} alarms configured")
            
            return validation_results
            
        except ClientError as e:
            logger.error(f"Error validating alarms: {e}")
            return validation_results
    
    def validate_metric_filters(self) -> Dict[str, bool]:
        """
        Validate that all startup metric filters are configured correctly.
        
        Returns:
            Dictionary mapping metric filter names to validation status
        """
        logger.info("Validating startup metric filters")
        
        validation_results = {}
        
        # Expected metric filters
        expected_filters = [
            f"{self.name_prefix}-minimal-phase-completion",
            f"{self.name_prefix}-essential-phase-completion",
            f"{self.name_prefix}-full-phase-completion",
            f"{self.name_prefix}-model-loading-success",
            f"{self.name_prefix}-model-loading-failure",
            f"{self.name_prefix}-model-loading-duration",
            f"{self.name_prefix}-user-wait-time",
            f"{self.name_prefix}-fallback-response-usage",
            f"{self.name_prefix}-model-cache-hit",
            f"{self.name_prefix}-model-cache-miss",
            f"{self.name_prefix}-health-check-failure"
        ]
        
        try:
            # Get log group name
            log_group_name = f"/aws/application/{self.name_prefix}"
            
            # Get all metric filters for the log group
            response = self.logs_client.describe_metric_filters(
                logGroupName=log_group_name
            )
            
            existing_filters = {f['filterName'] for f in response.get('metricFilters', [])}
            
            # Validate each expected filter
            for filter_name in expected_filters:
                exists = filter_name in existing_filters
                validation_results[filter_name] = exists
                
                if exists:
                    logger.info(f"✓ Metric filter configured: {filter_name}")
                else:
                    logger.warning(f"✗ Metric filter missing: {filter_name}")
            
            # Summary
            configured_count = sum(validation_results.values())
            total_count = len(expected_filters)
            logger.info(f"Metric filter validation: {configured_count}/{total_count} filters configured")
            
            return validation_results
            
        except ClientError as e:
            logger.error(f"Error validating metric filters: {e}")
            return validation_results
    
    def validate_dashboards(self) -> Dict[str, bool]:
        """
        Validate that startup monitoring dashboards are configured.
        
        Returns:
            Dictionary mapping dashboard names to validation status
        """
        logger.info("Validating startup monitoring dashboards")
        
        validation_results = {}
        
        # Expected dashboards
        expected_dashboards = [
            f"{self.name_prefix}-startup-monitoring",
            f"{self.name_prefix}-operational-dashboard"
        ]
        
        try:
            # Get all dashboards
            response = self.cloudwatch_client.list_dashboards()
            existing_dashboards = {d['DashboardName'] for d in response.get('DashboardEntries', [])}
            
            # Validate each expected dashboard
            for dashboard_name in expected_dashboards:
                exists = dashboard_name in existing_dashboards
                validation_results[dashboard_name] = exists
                
                if exists:
                    logger.info(f"✓ Dashboard configured: {dashboard_name}")
                else:
                    logger.warning(f"✗ Dashboard missing: {dashboard_name}")
            
            # Summary
            configured_count = sum(validation_results.values())
            total_count = len(expected_dashboards)
            logger.info(f"Dashboard validation: {configured_count}/{total_count} dashboards configured")
            
            return validation_results
            
        except ClientError as e:
            logger.error(f"Error validating dashboards: {e}")
            return validation_results
    
    def test_alarm_actions(self) -> bool:
        """
        Test that alarm actions are properly configured.
        
        Returns:
            True if all alarm actions are valid, False otherwise
        """
        logger.info("Testing alarm action configurations")
        
        try:
            # Get startup alerts topic ARN
            topics = self.sns_client.list_topics()
            startup_topic_arn = None
            
            for topic in topics.get('Topics', []):
                if f"{self.name_prefix}-startup-alerts" in topic['TopicArn']:
                    startup_topic_arn = topic['TopicArn']
                    break
            
            if not startup_topic_arn:
                logger.error("Startup alerts topic not found")
                return False
            
            # Check topic attributes
            response = self.sns_client.get_topic_attributes(TopicArn=startup_topic_arn)
            attributes = response.get('Attributes', {})
            
            logger.info(f"Topic ARN: {startup_topic_arn}")
            logger.info(f"Subscriptions confirmed: {attributes.get('SubscriptionsConfirmed', '0')}")
            logger.info(f"Subscriptions pending: {attributes.get('SubscriptionsPending', '0')}")
            
            # List subscriptions
            subscriptions = self.sns_client.list_subscriptions_by_topic(TopicArn=startup_topic_arn)
            
            for sub in subscriptions.get('Subscriptions', []):
                status = "✓" if sub['SubscriptionArn'] != 'PendingConfirmation' else "⏳"
                logger.info(f"{status} Subscription: {sub['Protocol']} - {sub['Endpoint']}")
            
            return True
            
        except ClientError as e:
            logger.error(f"Error testing alarm actions: {e}")
            return False
    
    def generate_configuration_report(self) -> Dict[str, any]:
        """
        Generate a comprehensive configuration report.
        
        Returns:
            Dictionary containing configuration status
        """
        logger.info("Generating configuration report")
        
        report = {
            "environment": self.environment,
            "region": self.region,
            "name_prefix": self.name_prefix,
            "timestamp": boto3.client('sts').get_caller_identity()['Account'],
            "alarms": self.validate_alarms(),
            "metric_filters": self.validate_metric_filters(),
            "dashboards": self.validate_dashboards(),
            "alarm_actions_valid": self.test_alarm_actions()
        }
        
        # Calculate overall status
        alarms_ok = all(report["alarms"].values())
        filters_ok = all(report["metric_filters"].values())
        dashboards_ok = all(report["dashboards"].values())
        actions_ok = report["alarm_actions_valid"]
        
        report["overall_status"] = "CONFIGURED" if (alarms_ok and filters_ok and dashboards_ok and actions_ok) else "INCOMPLETE"
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("CONFIGURATION REPORT SUMMARY")
        logger.info("="*60)
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Region: {self.region}")
        logger.info(f"Overall Status: {report['overall_status']}")
        logger.info(f"Alarms: {sum(report['alarms'].values())}/{len(report['alarms'])} configured")
        logger.info(f"Metric Filters: {sum(report['metric_filters'].values())}/{len(report['metric_filters'])} configured")
        logger.info(f"Dashboards: {sum(report['dashboards'].values())}/{len(report['dashboards'])} configured")
        logger.info(f"Alarm Actions: {'Valid' if actions_ok else 'Invalid'}")
        logger.info("="*60)
        
        return report
    
    def save_report(self, report: Dict[str, any], output_file: str) -> None:
        """Save configuration report to file."""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Configuration report saved to: {output_file}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Configure startup monitoring and alerting"
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment to configure"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--email",
        action="append",
        help="Email address for alert notifications (can be specified multiple times)"
    )
    parser.add_argument(
        "--phone",
        action="append",
        help="Phone number for SMS alerts (can be specified multiple times)"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate configuration without making changes"
    )
    parser.add_argument(
        "--output",
        default="startup-monitoring-config-report.json",
        help="Output file for configuration report"
    )
    
    args = parser.parse_args()
    
    # Initialize configurator
    configurator = StartupMonitoringConfigurator(
        environment=args.environment,
        region=args.region
    )
    
    try:
        # Configure SNS subscriptions (unless validate-only)
        if not args.validate_only and args.email:
            subscriptions = configurator.configure_sns_subscriptions(
                email_addresses=args.email,
                phone_numbers=args.phone
            )
            logger.info(f"Configured {len(subscriptions)} SNS subscriptions")
        
        # Generate configuration report
        report = configurator.generate_configuration_report()
        
        # Save report
        configurator.save_report(report, args.output)
        
        # Exit with appropriate code
        if report["overall_status"] == "CONFIGURED":
            logger.info("✓ Startup monitoring is fully configured")
            sys.exit(0)
        else:
            logger.warning("⚠ Startup monitoring configuration is incomplete")
            logger.warning("Run 'terraform apply' to complete the configuration")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Configuration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
