#!/usr/bin/env python3
"""
Deployment rollback script.
Rolls back ECS service to previous stable version.
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


class DeploymentRollback:
    """Manages deployment rollback operations."""
    
    def __init__(self, environment: str, aws_region: str = 'us-east-1'):
        self.environment = environment
        self.aws_region = aws_region
        
        # AWS clients
        self.ecs_client = boto3.client('ecs', region_name=aws_region)
        self.ecr_client = boto3.client('ecr', region_name=aws_region)
        self.ssm_client = boto3.client('ssm', region_name=aws_region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=aws_region)
        
        # Resource naming
        self.cluster_name = f'multimodal-librarian-{environment}'
        self.service_name = f'multimodal-librarian-{environment}'
        self.repository_name = 'multimodal-librarian'
        
    def get_current_deployment(self) -> Dict:
        """Get current deployment information."""
        try:
            response = self.ecs_client.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if not response['services']:
                raise ValueError(f"Service {self.service_name} not found")
            
            service = response['services'][0]
            
            # Get task definition
            task_def_response = self.ecs_client.describe_task_definition(
                taskDefinition=service['taskDefinition']
            )
            
            task_definition = task_def_response['taskDefinition']
            
            # Extract image tag from container definition
            container_def = task_definition['containerDefinitions'][0]
            image_uri = container_def['image']
            image_tag = image_uri.split(':')[-1] if ':' in image_uri else 'latest'
            
            return {
                'service_arn': service['serviceArn'],
                'task_definition_arn': service['taskDefinition'],
                'task_definition': task_definition,
                'current_image_tag': image_tag,
                'running_count': service['runningCount'],
                'desired_count': service['desiredCount'],
                'status': service['status']
            }
            
        except ClientError as e:
            logger.error(f"Failed to get current deployment: {str(e)}")
            raise
    
    def get_deployment_history(self, limit: int = 10) -> List[Dict]:
        """Get deployment history from Parameter Store."""
        try:
            # Get deployment history
            history_param = f'/multimodal-librarian/{self.environment}/deployment-history'
            
            try:
                response = self.ssm_client.get_parameter(Name=history_param)
                history = json.loads(response['Parameter']['Value'])
            except ClientError:
                # No history found
                logger.warning("No deployment history found")
                return []
            
            # Sort by timestamp (most recent first)
            history.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return history[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get deployment history: {str(e)}")
            return []
    
    def get_stable_versions(self) -> List[str]:
        """Get list of stable image versions from ECR."""
        try:
            response = self.ecr_client.describe_images(
                repositoryName=self.repository_name,
                filter={'tagStatus': 'TAGGED'},
                maxResults=20
            )
            
            # Filter for stable tags (exclude 'latest' and temporary tags)
            stable_images = []
            for image in response['imageDetails']:
                if 'imageTags' in image:
                    for tag in image['imageTags']:
                        if (tag != 'latest' and 
                            not tag.startswith('temp-') and
                            len(tag) >= 7):  # Assume commit SHA or semantic version
                            stable_images.append({
                                'tag': tag,
                                'pushed_at': image['imagePushedAt'],
                                'size': image['imageSizeInBytes']
                            })
            
            # Sort by push date (most recent first)
            stable_images.sort(key=lambda x: x['pushed_at'], reverse=True)
            
            return stable_images
            
        except ClientError as e:
            logger.error(f"Failed to get stable versions: {str(e)}")
            return []
    
    def validate_target_version(self, target_tag: str) -> bool:
        """Validate that the target version exists and is stable."""
        try:
            response = self.ecr_client.describe_images(
                repositoryName=self.repository_name,
                imageIds=[{'imageTag': target_tag}]
            )
            
            if not response['imageDetails']:
                logger.error(f"Image tag {target_tag} not found in ECR")
                return False
            
            # Check if this version was previously deployed successfully
            history = self.get_deployment_history()
            
            successful_deployments = [
                h for h in history 
                if h['image_tag'] == target_tag and h['status'] == 'success'
            ]
            
            if not successful_deployments:
                logger.warning(f"No successful deployment history found for {target_tag}")
                # Allow rollback but warn user
            
            return True
            
        except ClientError as e:
            logger.error(f"Failed to validate target version: {str(e)}")
            return False
    
    def create_rollback_task_definition(self, current_task_def: Dict, 
                                      target_tag: str) -> str:
        """Create new task definition for rollback."""
        try:
            # Clone current task definition
            new_task_def = {
                'family': current_task_def['family'],
                'taskRoleArn': current_task_def.get('taskRoleArn'),
                'executionRoleArn': current_task_def.get('executionRoleArn'),
                'networkMode': current_task_def.get('networkMode'),
                'requiresCompatibilities': current_task_def.get('requiresCompatibilities', []),
                'cpu': current_task_def.get('cpu'),
                'memory': current_task_def.get('memory'),
                'containerDefinitions': []
            }
            
            # Update container definitions with target image
            for container_def in current_task_def['containerDefinitions']:
                new_container_def = container_def.copy()
                
                # Update image URI with target tag
                image_parts = container_def['image'].split(':')
                if len(image_parts) > 1:
                    new_image_uri = f"{image_parts[0]}:{target_tag}"
                else:
                    new_image_uri = f"{container_def['image']}:{target_tag}"
                
                new_container_def['image'] = new_image_uri
                new_task_def['containerDefinitions'].append(new_container_def)
            
            # Register new task definition
            response = self.ecs_client.register_task_definition(**new_task_def)
            
            new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
            logger.info(f"Created rollback task definition: {new_task_def_arn}")
            
            return new_task_def_arn
            
        except ClientError as e:
            logger.error(f"Failed to create rollback task definition: {str(e)}")
            raise
    
    def perform_rollback(self, target_tag: str, 
                        deployment_strategy: str = 'rolling') -> bool:
        """Perform the actual rollback."""
        logger.info(f"Starting rollback to version {target_tag}...")
        
        try:
            # Get current deployment info
            current_deployment = self.get_current_deployment()
            
            if current_deployment['current_image_tag'] == target_tag:
                logger.info(f"Service is already running target version {target_tag}")
                return True
            
            # Create rollback task definition
            rollback_task_def_arn = self.create_rollback_task_definition(
                current_deployment['task_definition'], target_tag
            )
            
            # Record rollback start
            self.record_rollback_event('started', target_tag, current_deployment)
            
            # Update ECS service
            logger.info("Updating ECS service with rollback task definition...")
            
            update_params = {
                'cluster': self.cluster_name,
                'service': self.service_name,
                'taskDefinition': rollback_task_def_arn
            }
            
            if deployment_strategy == 'blue-green':
                # For blue-green, we need to handle this differently
                # This is a simplified version - full implementation would
                # involve creating new service and switching load balancer
                update_params['deploymentConfiguration'] = {
                    'maximumPercent': 200,
                    'minimumHealthyPercent': 100
                }
            else:
                # Rolling deployment
                update_params['deploymentConfiguration'] = {
                    'maximumPercent': 150,
                    'minimumHealthyPercent': 50
                }
            
            self.ecs_client.update_service(**update_params)
            
            # Wait for deployment to complete
            logger.info("Waiting for rollback deployment to complete...")
            
            waiter = self.ecs_client.get_waiter('services_stable')
            waiter.wait(
                cluster=self.cluster_name,
                services=[self.service_name],
                WaiterConfig={
                    'delay': 15,
                    'maxAttempts': 40  # 10 minutes max
                }
            )
            
            # Verify rollback success
            if self.verify_rollback_success(target_tag):
                logger.info("Rollback completed successfully")
                self.record_rollback_event('completed', target_tag, current_deployment)
                self.update_stable_version(target_tag)
                return True
            else:
                logger.error("Rollback verification failed")
                self.record_rollback_event('failed', target_tag, current_deployment)
                return False
                
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            self.record_rollback_event('failed', target_tag, 
                                     current_deployment if 'current_deployment' in locals() else {})
            return False
    
    def verify_rollback_success(self, target_tag: str) -> bool:
        """Verify that rollback was successful."""
        try:
            # Check service status
            current_deployment = self.get_current_deployment()
            
            if current_deployment['current_image_tag'] != target_tag:
                logger.error(f"Service not running target version. "
                           f"Expected: {target_tag}, "
                           f"Actual: {current_deployment['current_image_tag']}")
                return False
            
            if current_deployment['status'] != 'ACTIVE':
                logger.error(f"Service status is {current_deployment['status']}, expected ACTIVE")
                return False
            
            if current_deployment['running_count'] < current_deployment['desired_count']:
                logger.error(f"Not all tasks are running. "
                           f"Running: {current_deployment['running_count']}, "
                           f"Desired: {current_deployment['desired_count']}")
                return False
            
            # Check task health
            tasks_response = self.ecs_client.list_tasks(
                cluster=self.cluster_name,
                serviceName=self.service_name
            )
            
            if tasks_response['taskArns']:
                tasks_detail = self.ecs_client.describe_tasks(
                    cluster=self.cluster_name,
                    tasks=tasks_response['taskArns']
                )
                
                unhealthy_tasks = [
                    task for task in tasks_detail['tasks']
                    if task['lastStatus'] != 'RUNNING'
                ]
                
                if unhealthy_tasks:
                    logger.error(f"Found {len(unhealthy_tasks)} unhealthy tasks")
                    return False
            
            logger.info("Rollback verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Rollback verification failed: {str(e)}")
            return False
    
    def record_rollback_event(self, status: str, target_tag: str, 
                             deployment_info: Dict):
        """Record rollback event in deployment history."""
        try:
            event = {
                'timestamp': time.time(),
                'type': 'rollback',
                'status': status,
                'target_tag': target_tag,
                'previous_tag': deployment_info.get('current_image_tag'),
                'environment': self.environment,
                'initiated_by': 'automated-rollback'
            }
            
            # Get existing history
            history_param = f'/multimodal-librarian/{self.environment}/deployment-history'
            
            try:
                response = self.ssm_client.get_parameter(Name=history_param)
                history = json.loads(response['Parameter']['Value'])
            except ClientError:
                history = []
            
            # Add new event
            history.append(event)
            
            # Keep only last 50 events
            history = history[-50:]
            
            # Update parameter
            self.ssm_client.put_parameter(
                Name=history_param,
                Value=json.dumps(history),
                Type='String',
                Overwrite=True
            )
            
        except Exception as e:
            logger.error(f"Failed to record rollback event: {str(e)}")
    
    def update_stable_version(self, tag: str):
        """Update the last stable version parameter."""
        try:
            self.ssm_client.put_parameter(
                Name=f'/multimodal-librarian/{self.environment}/last-stable-tag',
                Value=tag,
                Type='String',
                Overwrite=True
            )
            
            logger.info(f"Updated last stable version to: {tag}")
            
        except ClientError as e:
            logger.error(f"Failed to update stable version: {str(e)}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Rollback deployment')
    parser.add_argument('--environment', required=True,
                       choices=['staging', 'production'],
                       help='Target environment')
    parser.add_argument('--target-tag', 
                       help='Target image tag to rollback to')
    parser.add_argument('--list-versions', action='store_true',
                       help='List available stable versions')
    parser.add_argument('--deployment-strategy', 
                       choices=['rolling', 'blue-green'],
                       default='rolling',
                       help='Deployment strategy for rollback')
    parser.add_argument('--auto-select', action='store_true',
                       help='Automatically select the most recent stable version')
    
    args = parser.parse_args()
    
    rollback = DeploymentRollback(args.environment)
    
    try:
        if args.list_versions:
            # List available versions
            logger.info("Available stable versions:")
            stable_versions = rollback.get_stable_versions()
            
            for i, version in enumerate(stable_versions[:10]):  # Show top 10
                logger.info(f"  {i+1}. {version['tag']} "
                          f"(pushed: {version['pushed_at'].strftime('%Y-%m-%d %H:%M:%S')})")
            
            return 0
        
        # Determine target version
        target_tag = args.target_tag
        
        if args.auto_select:
            # Get the most recent stable version (excluding current)
            current_deployment = rollback.get_current_deployment()
            current_tag = current_deployment['current_image_tag']
            
            stable_versions = rollback.get_stable_versions()
            
            # Find the most recent version that's not the current one
            for version in stable_versions:
                if version['tag'] != current_tag:
                    target_tag = version['tag']
                    break
            
            if not target_tag:
                logger.error("No suitable rollback version found")
                return 1
            
            logger.info(f"Auto-selected rollback target: {target_tag}")
        
        if not target_tag:
            logger.error("Target tag must be specified or --auto-select used")
            return 1
        
        # Validate target version
        if not rollback.validate_target_version(target_tag):
            logger.error(f"Target version {target_tag} is not valid")
            return 1
        
        # Perform rollback
        success = rollback.perform_rollback(target_tag, args.deployment_strategy)
        
        if success:
            logger.info(f"Rollback to {target_tag} completed successfully")
            return 0
        else:
            logger.error(f"Rollback to {target_tag} failed")
            return 1
            
    except Exception as e:
        logger.error(f"Rollback operation failed: {str(e)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())