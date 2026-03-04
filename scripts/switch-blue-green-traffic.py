#!/usr/bin/env python3
"""
Blue-Green deployment traffic switching script.
Switches load balancer traffic from blue to green environment.
"""

import argparse
import json
import logging
import sys
import time
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BlueGreenSwitcher:
    """Manages blue-green deployment traffic switching."""
    
    def __init__(self, environment: str, aws_region: str = 'us-east-1'):
        self.environment = environment
        self.aws_region = aws_region
        
        # AWS clients
        self.elbv2_client = boto3.client('elbv2', region_name=aws_region)
        self.ecs_client = boto3.client('ecs', region_name=aws_region)
        self.ssm_client = boto3.client('ssm', region_name=aws_region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=aws_region)
        
        # Resource naming
        self.lb_name = f'multimodal-librarian-{environment}'
        self.cluster_name = f'multimodal-librarian-{environment}'
        
    def get_load_balancer_arn(self) -> str:
        """Get the ARN of the load balancer."""
        try:
            response = self.elbv2_client.describe_load_balancers(
                Names=[self.lb_name]
            )
            
            if not response['LoadBalancers']:
                raise ValueError(f"Load balancer {self.lb_name} not found")
            
            return response['LoadBalancers'][0]['LoadBalancerArn']
            
        except ClientError as e:
            logger.error(f"Failed to get load balancer ARN: {str(e)}")
            raise
    
    def get_target_groups(self, lb_arn: str) -> Dict[str, Dict]:
        """Get target groups for the load balancer."""
        try:
            response = self.elbv2_client.describe_target_groups(
                LoadBalancerArn=lb_arn
            )
            
            target_groups = {}
            for tg in response['TargetGroups']:
                # Identify blue/green by tags or naming convention
                tags_response = self.elbv2_client.describe_tags(
                    ResourceArns=[tg['TargetGroupArn']]
                )
                
                tags = {tag['Key']: tag['Value'] 
                       for tag_desc in tags_response['TagDescriptions']
                       for tag in tag_desc['Tags']}
                
                deployment_type = tags.get('DeploymentType', 'unknown')
                if deployment_type in ['blue', 'green']:
                    target_groups[deployment_type] = {
                        'arn': tg['TargetGroupArn'],
                        'name': tg['TargetGroupName'],
                        'health_check_path': tg['HealthCheckPath']
                    }
            
            return target_groups
            
        except ClientError as e:
            logger.error(f"Failed to get target groups: {str(e)}")
            raise
    
    def get_listener_rules(self, lb_arn: str) -> List[Dict]:
        """Get listener rules for the load balancer."""
        try:
            # Get listeners
            listeners_response = self.elbv2_client.describe_listeners(
                LoadBalancerArn=lb_arn
            )
            
            rules = []
            for listener in listeners_response['Listeners']:
                rules_response = self.elbv2_client.describe_rules(
                    ListenerArn=listener['ListenerArn']
                )
                
                for rule in rules_response['Rules']:
                    rules.append({
                        'listener_arn': listener['ListenerArn'],
                        'rule_arn': rule['RuleArn'],
                        'priority': rule['Priority'],
                        'actions': rule['Actions'],
                        'conditions': rule['Conditions']
                    })
            
            return rules
            
        except ClientError as e:
            logger.error(f"Failed to get listener rules: {str(e)}")
            raise
    
    def validate_green_environment(self, green_tg_arn: str) -> bool:
        """Validate that the green environment is healthy."""
        logger.info("Validating green environment health...")
        
        try:
            # Check target health
            health_response = self.elbv2_client.describe_target_health(
                TargetGroupArn=green_tg_arn
            )
            
            healthy_targets = [
                target for target in health_response['TargetHealthDescriptions']
                if target['TargetHealth']['State'] == 'healthy'
            ]
            
            total_targets = len(health_response['TargetHealthDescriptions'])
            healthy_count = len(healthy_targets)
            
            logger.info(f"Green environment: {healthy_count}/{total_targets} targets healthy")
            
            if healthy_count == 0:
                logger.error("No healthy targets in green environment")
                return False
            
            if healthy_count < total_targets:
                logger.warning(f"Only {healthy_count}/{total_targets} targets healthy")
                # Continue if at least 50% are healthy
                return healthy_count >= (total_targets * 0.5)
            
            return True
            
        except ClientError as e:
            logger.error(f"Failed to validate green environment: {str(e)}")
            return False
    
    def perform_canary_test(self, green_tg_arn: str, canary_percentage: int = 10) -> bool:
        """Perform canary testing by routing small percentage to green."""
        logger.info(f"Starting canary test with {canary_percentage}% traffic...")
        
        try:
            # This would involve creating weighted routing rules
            # For simplicity, we'll simulate the canary test
            logger.info("Canary test simulation - checking green environment metrics...")
            
            # Wait for metrics to accumulate
            time.sleep(30)
            
            # Check error rates and response times
            end_time = time.time()
            start_time = end_time - 300  # Last 5 minutes
            
            # Get target group metrics
            metrics_response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/ApplicationELB',
                MetricName='HTTPCode_Target_5XX_Count',
                Dimensions=[
                    {
                        'Name': 'TargetGroup',
                        'Value': green_tg_arn.split('/')[-1]
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=['Sum']
            )
            
            error_count = sum(dp['Sum'] for dp in metrics_response['Datapoints'])
            
            if error_count > 0:
                logger.error(f"Green environment showing {error_count} 5xx errors")
                return False
            
            logger.info("Canary test passed - no errors detected")
            return True
            
        except ClientError as e:
            logger.error(f"Canary test failed: {str(e)}")
            return False
    
    def switch_traffic(self, blue_tg_arn: str, green_tg_arn: str, 
                      gradual: bool = True) -> bool:
        """Switch traffic from blue to green environment."""
        logger.info("Starting traffic switch from blue to green...")
        
        try:
            lb_arn = self.get_load_balancer_arn()
            rules = self.get_listener_rules(lb_arn)
            
            # Find the default rule that routes to blue
            default_rule = None
            for rule in rules:
                if rule['priority'] == 'default':
                    for action in rule['actions']:
                        if (action['Type'] == 'forward' and 
                            action['TargetGroupArn'] == blue_tg_arn):
                            default_rule = rule
                            break
            
            if not default_rule:
                logger.error("Could not find default rule routing to blue environment")
                return False
            
            if gradual:
                # Gradual switch: 50% -> 100%
                percentages = [50, 100]
            else:
                # Immediate switch
                percentages = [100]
            
            for percentage in percentages:
                logger.info(f"Switching {percentage}% of traffic to green...")
                
                if percentage == 100:
                    # Full switch - update default action
                    self.elbv2_client.modify_rule(
                        RuleArn=default_rule['rule_arn'],
                        Actions=[
                            {
                                'Type': 'forward',
                                'TargetGroupArn': green_tg_arn
                            }
                        ]
                    )
                else:
                    # Weighted routing
                    self.elbv2_client.modify_rule(
                        RuleArn=default_rule['rule_arn'],
                        Actions=[
                            {
                                'Type': 'forward',
                                'ForwardConfig': {
                                    'TargetGroups': [
                                        {
                                            'TargetGroupArn': blue_tg_arn,
                                            'Weight': 100 - percentage
                                        },
                                        {
                                            'TargetGroupArn': green_tg_arn,
                                            'Weight': percentage
                                        }
                                    ]
                                }
                            }
                        ]
                    )
                
                # Wait and monitor
                logger.info(f"Waiting 60 seconds to monitor traffic at {percentage}%...")
                time.sleep(60)
                
                # Check for errors
                if not self.monitor_switch_health(green_tg_arn):
                    logger.error(f"Health check failed at {percentage}% traffic")
                    return False
            
            logger.info("Traffic switch completed successfully")
            return True
            
        except ClientError as e:
            logger.error(f"Traffic switch failed: {str(e)}")
            return False
    
    def monitor_switch_health(self, green_tg_arn: str) -> bool:
        """Monitor health during traffic switch."""
        try:
            # Check target health
            health_response = self.elbv2_client.describe_target_health(
                TargetGroupArn=green_tg_arn
            )
            
            unhealthy_targets = [
                target for target in health_response['TargetHealthDescriptions']
                if target['TargetHealth']['State'] != 'healthy'
            ]
            
            if unhealthy_targets:
                logger.error(f"Found {len(unhealthy_targets)} unhealthy targets")
                return False
            
            # Check recent error rates
            end_time = time.time()
            start_time = end_time - 120  # Last 2 minutes
            
            metrics_response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/ApplicationELB',
                MetricName='HTTPCode_Target_5XX_Count',
                Dimensions=[
                    {
                        'Name': 'TargetGroup',
                        'Value': green_tg_arn.split('/')[-1]
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,
                Statistics=['Sum']
            )
            
            recent_errors = sum(dp['Sum'] for dp in metrics_response['Datapoints'])
            
            if recent_errors > 5:  # Allow up to 5 errors
                logger.error(f"High error rate detected: {recent_errors} errors")
                return False
            
            return True
            
        except ClientError as e:
            logger.error(f"Health monitoring failed: {str(e)}")
            return False
    
    def rollback_traffic(self, blue_tg_arn: str) -> bool:
        """Rollback traffic to blue environment."""
        logger.info("Rolling back traffic to blue environment...")
        
        try:
            lb_arn = self.get_load_balancer_arn()
            rules = self.get_listener_rules(lb_arn)
            
            # Find the default rule
            default_rule = None
            for rule in rules:
                if rule['priority'] == 'default':
                    default_rule = rule
                    break
            
            if not default_rule:
                logger.error("Could not find default rule")
                return False
            
            # Switch back to blue
            self.elbv2_client.modify_rule(
                RuleArn=default_rule['rule_arn'],
                Actions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': blue_tg_arn
                    }
                ]
            )
            
            logger.info("Traffic rollback completed")
            return True
            
        except ClientError as e:
            logger.error(f"Traffic rollback failed: {str(e)}")
            return False
    
    def update_deployment_state(self, active_environment: str):
        """Update deployment state in Parameter Store."""
        try:
            self.ssm_client.put_parameter(
                Name=f'/multimodal-librarian/{self.environment}/active-deployment',
                Value=active_environment,
                Type='String',
                Overwrite=True
            )
            
            logger.info(f"Updated active deployment to: {active_environment}")
            
        except ClientError as e:
            logger.error(f"Failed to update deployment state: {str(e)}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Switch blue-green deployment traffic')
    parser.add_argument('--environment', required=True, 
                       choices=['staging', 'production'],
                       help='Target environment')
    parser.add_argument('--canary-test', action='store_true',
                       help='Perform canary testing before full switch')
    parser.add_argument('--gradual', action='store_true', default=True,
                       help='Perform gradual traffic switch')
    parser.add_argument('--rollback', action='store_true',
                       help='Rollback to blue environment')
    
    args = parser.parse_args()
    
    logger.info(f"Starting blue-green traffic switch for {args.environment}...")
    
    switcher = BlueGreenSwitcher(args.environment)
    
    try:
        # Get load balancer and target groups
        lb_arn = switcher.get_load_balancer_arn()
        target_groups = switcher.get_target_groups(lb_arn)
        
        if 'blue' not in target_groups or 'green' not in target_groups:
            logger.error("Could not find both blue and green target groups")
            return 1
        
        blue_tg_arn = target_groups['blue']['arn']
        green_tg_arn = target_groups['green']['arn']
        
        logger.info(f"Blue target group: {target_groups['blue']['name']}")
        logger.info(f"Green target group: {target_groups['green']['name']}")
        
        if args.rollback:
            # Rollback to blue
            success = switcher.rollback_traffic(blue_tg_arn)
            if success:
                switcher.update_deployment_state('blue')
        else:
            # Validate green environment
            if not switcher.validate_green_environment(green_tg_arn):
                logger.error("Green environment validation failed")
                return 1
            
            # Perform canary test if requested
            if args.canary_test:
                if not switcher.perform_canary_test(green_tg_arn):
                    logger.error("Canary test failed")
                    return 1
            
            # Switch traffic to green
            success = switcher.switch_traffic(
                blue_tg_arn, green_tg_arn, gradual=args.gradual
            )
            
            if success:
                switcher.update_deployment_state('green')
            else:
                # Auto-rollback on failure
                logger.info("Switching failed, performing automatic rollback...")
                switcher.rollback_traffic(blue_tg_arn)
                return 1
        
        logger.info("Blue-green traffic switch completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Blue-green switch failed: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())