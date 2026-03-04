#!/usr/bin/env python3
"""
Deploy with Disabled Features

This script updates the ECS task definition to disable OpenSearch and Neptune
during startup, allowing the application to start successfully without these dependencies.

Usage:
    python scripts/deploy-with-disabled-features.py
"""

import json
import boto3
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
REGION = "us-east-1"


def get_current_task_definition():
    """Get the current task definition."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        # Get service to find current task definition
        response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if not response['services']:
            logger.error(f"Service {SERVICE_NAME} not found")
            return None
        
        task_def_arn = response['services'][0]['taskDefinition']
        logger.info(f"Current task definition: {task_def_arn}")
        
        # Get task definition details
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=task_def_arn
        )
        
        return task_def_response['taskDefinition']
        
    except Exception as e:
        logger.error(f"Failed to get current task definition: {e}")
        return None


def update_task_definition_with_disabled_features(task_def):
    """Update task definition to disable OpenSearch and Neptune."""
    try:
        # Find the main container
        container = None
        for c in task_def['containerDefinitions']:
            if 'multimodal' in c['name'].lower():
                container = c
                break
        
        if not container:
            logger.error("Could not find main container in task definition")
            return None
        
        logger.info(f"Found container: {container['name']}")
        
        # Get current environment variables
        env_vars = container.get('environment', [])
        env_dict = {var['name']: var['value'] for var in env_vars}
        
        # Add/update environment variables to disable features
        env_dict['ENABLE_VECTOR_SEARCH'] = 'false'
        env_dict['ENABLE_GRAPH_DB'] = 'false'
        
        # Also ensure we're not trying to connect to these services on startup
        env_dict['SKIP_OPENSEARCH_INIT'] = 'true'
        env_dict['SKIP_NEPTUNE_INIT'] = 'true'
        
        logger.info("Updated environment variables:")
        logger.info(f"  ENABLE_VECTOR_SEARCH: {env_dict['ENABLE_VECTOR_SEARCH']}")
        logger.info(f"  ENABLE_GRAPH_DB: {env_dict['ENABLE_GRAPH_DB']}")
        logger.info(f"  SKIP_OPENSEARCH_INIT: {env_dict['SKIP_OPENSEARCH_INIT']}")
        logger.info(f"  SKIP_NEPTUNE_INIT: {env_dict['SKIP_NEPTUNE_INIT']}")
        
        # Convert back to list format
        container['environment'] = [
            {'name': k, 'value': str(v)} for k, v in env_dict.items()
        ]
        
        return task_def
        
    except Exception as e:
        logger.error(f"Failed to update task definition: {e}")
        return None


def register_new_task_definition(task_def):
    """Register a new task definition revision."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        # Remove fields that shouldn't be in registration request
        fields_to_remove = [
            'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
            'compatibilities', 'registeredAt', 'registeredBy', 'deregisteredAt'
        ]
        
        for field in fields_to_remove:
            task_def.pop(field, None)
        
        # Register new task definition
        logger.info("Registering new task definition...")
        response = ecs_client.register_task_definition(**task_def)
        
        new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
        new_revision = response['taskDefinition']['revision']
        
        logger.info(f"✓ Registered new task definition: {new_task_def_arn}")
        logger.info(f"  Revision: {new_revision}")
        
        return new_task_def_arn
        
    except Exception as e:
        logger.error(f"Failed to register task definition: {e}")
        return None


def update_service(new_task_def_arn):
    """Update the ECS service to use the new task definition."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        logger.info(f"Updating service {SERVICE_NAME} to use new task definition...")
        
        response = ecs_client.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True
        )
        
        logger.info("✓ Service update initiated")
        logger.info(f"  Deployment ID: {response['service']['deployments'][0]['id']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to update service: {e}")
        return False


def wait_for_deployment(timeout_minutes=15):
    """Wait for the deployment to complete."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        
        logger.info(f"Waiting for deployment to complete (timeout: {timeout_minutes} minutes)...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                logger.error("Deployment timed out")
                return False
            
            # Get service status
            response = ecs_client.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            if not response['services']:
                logger.error("Service not found")
                return False
            
            service = response['services'][0]
            deployments = service['deployments']
            
            # Check if we have only one deployment (the new one)
            if len(deployments) == 1:
                deployment = deployments[0]
                
                if deployment['status'] == 'PRIMARY':
                    running_count = deployment['runningCount']
                    desired_count = deployment['desiredCount']
                    
                    logger.info(f"  Running: {running_count}/{desired_count} tasks")
                    
                    if running_count == desired_count and running_count > 0:
                        logger.info("✓ Deployment completed successfully!")
                        return True
            else:
                logger.info(f"  Multiple deployments active: {len(deployments)}")
            
            # Wait before checking again
            time.sleep(30)
        
    except Exception as e:
        logger.error(f"Error waiting for deployment: {e}")
        return False


def verify_health_check():
    """Verify that the health check endpoint is responding."""
    try:
        ecs_client = boto3.client('ecs', region_name=REGION)
        elbv2_client = boto3.client('elbv2', region_name=REGION)
        
        # Get service details
        response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if not response['services']:
            logger.error("Service not found")
            return False
        
        service = response['services'][0]
        
        # Get load balancer info
        if service.get('loadBalancers'):
            target_group_arn = service['loadBalancers'][0]['targetGroupArn']
            
            # Check target health
            health_response = elbv2_client.describe_target_health(
                TargetGroupArn=target_group_arn
            )
            
            healthy_targets = [
                t for t in health_response['TargetHealthDescriptions']
                if t['TargetHealth']['State'] == 'healthy'
            ]
            
            total_targets = len(health_response['TargetHealthDescriptions'])
            
            logger.info(f"Target health: {len(healthy_targets)}/{total_targets} healthy")
            
            if healthy_targets:
                logger.info("✓ Health check is passing!")
                return True
            else:
                logger.warning("⚠ No healthy targets yet")
                
                # Show target health details
                for target in health_response['TargetHealthDescriptions']:
                    state = target['TargetHealth']['State']
                    reason = target['TargetHealth'].get('Reason', 'N/A')
                    description = target['TargetHealth'].get('Description', 'N/A')
                    logger.info(f"  Target: {state} - {reason} - {description}")
                
                return False
        else:
            logger.warning("No load balancer configured for service")
            return False
        
    except Exception as e:
        logger.error(f"Failed to verify health check: {e}")
        return False


def main():
    """Main execution function."""
    logger.info("=" * 80)
    logger.info("DEPLOYING WITH DISABLED FEATURES")
    logger.info("=" * 80)
    
    # Step 1: Get current task definition
    logger.info("\n1. Getting current task definition...")
    task_def = get_current_task_definition()
    if not task_def:
        logger.error("Failed to get current task definition")
        return 1
    
    # Step 2: Update task definition
    logger.info("\n2. Updating task definition to disable OpenSearch and Neptune...")
    updated_task_def = update_task_definition_with_disabled_features(task_def)
    if not updated_task_def:
        logger.error("Failed to update task definition")
        return 1
    
    # Step 3: Register new task definition
    logger.info("\n3. Registering new task definition...")
    new_task_def_arn = register_new_task_definition(updated_task_def)
    if not new_task_def_arn:
        logger.error("Failed to register new task definition")
        return 1
    
    # Step 4: Update service
    logger.info("\n4. Updating ECS service...")
    if not update_service(new_task_def_arn):
        logger.error("Failed to update service")
        return 1
    
    # Step 5: Wait for deployment
    logger.info("\n5. Waiting for deployment to complete...")
    if not wait_for_deployment():
        logger.error("Deployment did not complete successfully")
        logger.info("\nYou can check the deployment status with:")
        logger.info(f"  aws ecs describe-services --cluster {CLUSTER_NAME} --services {SERVICE_NAME}")
        return 1
    
    # Step 6: Verify health check
    logger.info("\n6. Verifying health check...")
    time.sleep(30)  # Wait a bit for health checks to stabilize
    verify_health_check()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("DEPLOYMENT COMPLETE")
    logger.info("=" * 80)
    logger.info("\n✓ Application deployed with OpenSearch and Neptune disabled")
    logger.info("\nThe application should now start successfully without these dependencies.")
    logger.info("\nNext steps:")
    logger.info("1. Monitor the application logs for any errors")
    logger.info("2. Test the health check endpoint: /health/simple")
    logger.info("3. Once stable, you can gradually re-enable features")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
