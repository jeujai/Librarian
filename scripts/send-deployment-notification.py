#!/usr/bin/env python3
"""
Deployment notification script.
Sends notifications about deployment status to various channels.
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin

import boto3
import requests
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeploymentNotifier:
    """Handles deployment notifications across multiple channels."""
    
    def __init__(self, environment: str, aws_region: str = 'us-east-1'):
        self.environment = environment
        self.aws_region = aws_region
        
        # AWS clients
        self.sns_client = boto3.client('sns', region_name=aws_region)
        self.ssm_client = boto3.client('ssm', region_name=aws_region)
        
    def get_notification_config(self) -> Dict:
        """Get notification configuration from Parameter Store."""
        try:
            config_param = f'/multimodal-librarian/{self.environment}/notification-config'
            
            response = self.ssm_client.get_parameter(Name=config_param)
            config = json.loads(response['Parameter']['Value'])
            
            return config
            
        except ClientError:
            # Return default configuration
            logger.warning("No notification config found, using defaults")
            return {
                'sns_topics': [],
                'slack_webhooks': [],
                'email_addresses': [],
                'teams_webhooks': []
            }
    
    def send_sns_notification(self, topic_arn: str, subject: str, 
                             message: str) -> bool:
        """Send notification via SNS."""
        try:
            self.sns_client.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=message
            )
            
            logger.info(f"SNS notification sent to {topic_arn}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to send SNS notification: {str(e)}")
            return False
    
    def send_slack_notification(self, webhook_url: str, 
                               notification_data: Dict) -> bool:
        """Send notification to Slack."""
        try:
            # Format Slack message
            color = self.get_status_color(notification_data['status'])
            
            slack_payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"Deployment {notification_data['status'].title()}",
                        "fields": [
                            {
                                "title": "Environment",
                                "value": notification_data['environment'],
                                "short": True
                            },
                            {
                                "title": "Version",
                                "value": notification_data['image_tag'],
                                "short": True
                            },
                            {
                                "title": "Strategy",
                                "value": notification_data.get('strategy', 'rolling'),
                                "short": True
                            },
                            {
                                "title": "Duration",
                                "value": notification_data.get('duration', 'N/A'),
                                "short": True
                            }
                        ],
                        "footer": "Multimodal Librarian Deployment",
                        "ts": int(time.time())
                    }
                ]
            }
            
            # Add additional fields based on status
            if notification_data['status'] == 'success':
                slack_payload['attachments'][0]['fields'].extend([
                    {
                        "title": "Application URL",
                        "value": notification_data.get('app_url', 'N/A'),
                        "short": False
                    }
                ])
            elif notification_data['status'] == 'failed':
                slack_payload['attachments'][0]['fields'].extend([
                    {
                        "title": "Error",
                        "value": notification_data.get('error', 'Unknown error'),
                        "short": False
                    },
                    {
                        "title": "Rollback Status",
                        "value": notification_data.get('rollback_status', 'Not performed'),
                        "short": True
                    }
                ])
            
            response = requests.post(webhook_url, json=slack_payload, timeout=10)
            response.raise_for_status()
            
            logger.info("Slack notification sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {str(e)}")
            return False
    
    def send_teams_notification(self, webhook_url: str, 
                               notification_data: Dict) -> bool:
        """Send notification to Microsoft Teams."""
        try:
            # Format Teams message
            color = self.get_status_color(notification_data['status'])
            
            teams_payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": color.replace('#', ''),
                "summary": f"Deployment {notification_data['status']}",
                "sections": [
                    {
                        "activityTitle": f"Deployment {notification_data['status'].title()}",
                        "activitySubtitle": f"Environment: {notification_data['environment']}",
                        "facts": [
                            {
                                "name": "Version",
                                "value": notification_data['image_tag']
                            },
                            {
                                "name": "Strategy",
                                "value": notification_data.get('strategy', 'rolling')
                            },
                            {
                                "name": "Duration",
                                "value": notification_data.get('duration', 'N/A')
                            },
                            {
                                "name": "Timestamp",
                                "value": time.strftime('%Y-%m-%d %H:%M:%S UTC', 
                                                    time.gmtime())
                            }
                        ],
                        "markdown": True
                    }
                ]
            }
            
            # Add status-specific information
            if notification_data['status'] == 'success':
                teams_payload['sections'][0]['facts'].append({
                    "name": "Application URL",
                    "value": notification_data.get('app_url', 'N/A')
                })
            elif notification_data['status'] == 'failed':
                teams_payload['sections'][0]['facts'].extend([
                    {
                        "name": "Error",
                        "value": notification_data.get('error', 'Unknown error')
                    },
                    {
                        "name": "Rollback Status",
                        "value": notification_data.get('rollback_status', 'Not performed')
                    }
                ])
            
            response = requests.post(webhook_url, json=teams_payload, timeout=10)
            response.raise_for_status()
            
            logger.info("Teams notification sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Teams notification: {str(e)}")
            return False
    
    def get_status_color(self, status: str) -> str:
        """Get color code for deployment status."""
        colors = {
            'success': '#36a64f',  # Green
            'failed': '#ff0000',   # Red
            'started': '#ffaa00',  # Orange
            'warning': '#ffaa00'   # Orange
        }
        return colors.get(status, '#808080')  # Gray for unknown
    
    def format_text_message(self, notification_data: Dict) -> str:
        """Format plain text message for email/SMS."""
        status = notification_data['status'].upper()
        environment = notification_data['environment'].upper()
        
        message = f"DEPLOYMENT {status}\n"
        message += f"Environment: {environment}\n"
        message += f"Version: {notification_data['image_tag']}\n"
        message += f"Strategy: {notification_data.get('strategy', 'rolling')}\n"
        
        if notification_data.get('duration'):
            message += f"Duration: {notification_data['duration']}\n"
        
        message += f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        
        if notification_data['status'] == 'success':
            message += f"\nApplication URL: {notification_data.get('app_url', 'N/A')}\n"
            message += "All services are healthy and operational."
        elif notification_data['status'] == 'failed':
            message += f"\nError: {notification_data.get('error', 'Unknown error')}\n"
            message += f"Rollback Status: {notification_data.get('rollback_status', 'Not performed')}\n"
            message += "Please check the deployment logs for more details."
        
        return message
    
    def send_notifications(self, notification_data: Dict) -> Dict[str, bool]:
        """Send notifications to all configured channels."""
        logger.info(f"Sending deployment notifications for {notification_data['status']} status...")
        
        config = self.get_notification_config()
        results = {}
        
        # Format messages
        subject = (f"Deployment {notification_data['status'].title()} - "
                  f"{notification_data['environment'].title()} Environment")
        text_message = self.format_text_message(notification_data)
        
        # Send SNS notifications
        for topic_arn in config.get('sns_topics', []):
            success = self.send_sns_notification(topic_arn, subject, text_message)
            results[f'sns_{topic_arn.split(":")[-1]}'] = success
        
        # Send Slack notifications
        for webhook_url in config.get('slack_webhooks', []):
            success = self.send_slack_notification(webhook_url, notification_data)
            results[f'slack_{webhook_url.split("/")[-1][:8]}'] = success
        
        # Send Teams notifications
        for webhook_url in config.get('teams_webhooks', []):
            success = self.send_teams_notification(webhook_url, notification_data)
            results[f'teams_{webhook_url.split("/")[-1][:8]}'] = success
        
        # Log results
        successful_channels = sum(results.values())
        total_channels = len(results)
        
        logger.info(f"Notifications sent: {successful_channels}/{total_channels} successful")
        
        return results
    
    def send_rollback_notification(self, rollback_data: Dict) -> Dict[str, bool]:
        """Send rollback-specific notifications."""
        notification_data = {
            'status': 'rollback',
            'environment': rollback_data['environment'],
            'image_tag': rollback_data['target_tag'],
            'previous_tag': rollback_data.get('previous_tag'),
            'reason': rollback_data.get('reason', 'Automatic rollback'),
            'duration': rollback_data.get('duration')
        }
        
        return self.send_notifications(notification_data)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Send deployment notifications')
    parser.add_argument('--environment', required=True,
                       choices=['staging', 'production'],
                       help='Target environment')
    parser.add_argument('--status', required=True,
                       choices=['started', 'success', 'failed', 'rollback'],
                       help='Deployment status')
    parser.add_argument('--image-tag', required=True,
                       help='Deployed image tag')
    parser.add_argument('--strategy', 
                       choices=['rolling', 'blue-green'],
                       default='rolling',
                       help='Deployment strategy used')
    parser.add_argument('--duration',
                       help='Deployment duration (e.g., "5m 30s")')
    parser.add_argument('--app-url',
                       help='Application URL (for success notifications)')
    parser.add_argument('--error',
                       help='Error message (for failure notifications)')
    parser.add_argument('--rollback-status',
                       help='Rollback status (for failure notifications)')
    parser.add_argument('--previous-tag',
                       help='Previous image tag (for rollback notifications)')
    parser.add_argument('--reason',
                       help='Rollback reason (for rollback notifications)')
    
    args = parser.parse_args()
    
    notifier = DeploymentNotifier(args.environment)
    
    try:
        # Prepare notification data
        notification_data = {
            'status': args.status,
            'environment': args.environment,
            'image_tag': args.image_tag,
            'strategy': args.strategy
        }
        
        # Add optional fields
        if args.duration:
            notification_data['duration'] = args.duration
        if args.app_url:
            notification_data['app_url'] = args.app_url
        if args.error:
            notification_data['error'] = args.error
        if args.rollback_status:
            notification_data['rollback_status'] = args.rollback_status
        if args.previous_tag:
            notification_data['previous_tag'] = args.previous_tag
        if args.reason:
            notification_data['reason'] = args.reason
        
        # Send notifications
        if args.status == 'rollback':
            results = notifier.send_rollback_notification(notification_data)
        else:
            results = notifier.send_notifications(notification_data)
        
        # Check if all notifications were successful
        all_successful = all(results.values()) if results else True
        
        if all_successful:
            logger.info("All notifications sent successfully")
            return 0
        else:
            logger.warning("Some notifications failed to send")
            return 1
            
    except Exception as e:
        logger.error(f"Notification sending failed: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())