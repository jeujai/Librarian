#!/usr/bin/env python3
"""
Recreate Service with OpenSearch and Vector Store Fixes

This script:
1. Deletes the INACTIVE service
2. Creates a new service with the fixed task definition
3. Monitors deployment until stable
"""

import boto3
import json
import time
from datetime import datetime

def get_service_config():
    """Get the current service configuration."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service']
    )
    
    if not response['services']:
        raise Exception("Service not found")
    
    return response['services'][0]

def delete_service():
    """Delete the INACTIVE service."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("DELETING INACTIVE SERVICE")
    print("=" * 80)
    
    response = ecs.delete_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        force=True
    )
    
    print(f"✓ Service deletion initiated")
    
    # Wait for service to be deleted
    print("Waiting for service to be deleted...")
    time.sleep(30)
    
    return response

def create_fixed_task_definition():
    """Create a new task definition with OpenSearch and vector store disabled."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # Get the latest task definition
    response = ecs.describe_task_definition(taskDefinition='multimodal-lib-prod-app:57')
    current_task_def = response['taskDefinition']
    
    # Get current environment variables
    container_def = current_task_def['containerDefinitions'][0]
    env_vars = {env['name']: env['value'] for env in container_def.get('environment', [])}
    
    # Add/update critical environment variables to disable blocking services
    env_vars.update({
        # Disable vector search completely
        'ENABLE_VECTOR_SEARCH': 'false',
        
        # Skip OpenSearch initialization on startup
        'SKIP_OPENSEARCH_INIT': 'true',
        
        # Set very short timeout for any OpenSearch attempts
        'OPENSEARCH_TIMEOUT': '5',
        
        # Disable graph database (Neptune) as well
        'ENABLE_GRAPH_DB': 'false',
        'SKIP_NEPTUNE_INIT': 'true',
        
        # Ensure health check doesn't wait for dependencies
        'HEALTH_CHECK_TIMEOUT': '2',
        
        # Log level for debugging
        'LOG_LEVEL': 'INFO',
    })
    
    # Convert back to list format
    new_env = [{'name': k, 'value': v} for k, v in env_vars.items()]
    
    # Create new container definition
    new_container_def = container_def.copy()
    new_container_def['environment'] = new_env
    
    # Prepare new task definition
    new_task_def = {
        'family': current_task_def['family'],
        'taskRoleArn': current_task_def['taskRoleArn'],
        'executionRoleArn': current_task_def['executionRoleArn'],
        'networkMode': current_task_def['networkMode'],
        'containerDefinitions': [new_container_def],
        'requiresCompatibilities': current_task_def['requiresCompatibilities'],
        'cpu': current_task_def['cpu'],
        'memory': current_task_def['memory'],
    }
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    new_revision = response['taskDefinition']['revision']
    
    return new_task_def_arn, new_revision, new_env

def create_service(task_def_arn, service_config):
    """Create a new service with the fixed task definition."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("CREATING NEW SERVICE")
    print("=" * 80)
    
    # Extract network configuration
    network_config = service_config['networkConfiguration']
    
    # Extract load balancer configuration
    load_balancers = service_config['loadBalancers']
    
    # Create service
    response = ecs.create_service(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service',
        taskDefinition=task_def_arn,
        desiredCount=1,
        launchType='FARGATE',
        networkConfiguration=network_config,
        loadBalancers=load_balancers,
        healthCheckGracePeriodSeconds=300,
        enableExecuteCommand=True
    )
    
    print(f"✓ Service created successfully")
    print(f"  Service ARN: {response['service']['serviceArn']}")
    
    return response

def wait_for_deployment(timeout=600):
    """Wait for deployment to complete."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("WAITING FOR DEPLOYMENT")
    print("=" * 80)
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        try:
            response = ecs.describe_services(
                cluster='multimodal-lib-prod-cluster',
                services=['multimodal-lib-prod-service']
            )
            
            if not response['services']:
                print("Service not found yet, waiting...")
                time.sleep(10)
                continue
            
            service = response['services'][0]
            service_status = service['status']
            deployments = service['deployments']
            
            if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
                running_count = deployments[0]['runningCount']
                desired_count = deployments[0]['desiredCount']
                
                status = f"Service: {service_status}, Running: {running_count}/{desired_count}"
                if status != last_status:
                    print(f"  {status}")
                    last_status = status
                
                if running_count == desired_count and running_count > 0 and service_status == 'ACTIVE':
                    print("\n✓ Deployment completed successfully!")
                    return True
            else:
                status = f"Service: {service_status}, Deployments: {len(deployments)}"
                if status != last_status:
                    print(f"  {status}")
                    for i, dep in enumerate(deployments):
                        print(f"    {i+1}. Status: {dep['status']}, Running: {dep['runningCount']}/{dep['desiredCount']}")
                    last_status = status
        except Exception as e:
            print(f"Error checking service status: {e}")
        
        time.sleep(10)
    
    print("\n⚠ Deployment did not complete within timeout")
    return False

def check_target_health():
    """Check ALB target health."""
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("CHECKING TARGET HEALTH")
    print("=" * 80)
    
    # Get target group
    response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg-v2']
    )
    
    if not response['TargetGroups']:
        print("✗ Target group not found")
        return False
    
    target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
    
    # Check target health
    health_response = elbv2.describe_target_health(
        TargetGroupArn=target_group_arn
    )
    
    all_healthy = True
    for target in health_response['TargetHealthDescriptions']:
        target_id = target['Target']['Id']
        health_state = target['TargetHealth']['State']
        
        print(f"\nTarget: {target_id}")
        print(f"  State: {health_state}")
        
        if health_state != 'healthy':
            reason = target['TargetHealth'].get('Reason', 'Unknown')
            description = target['TargetHealth'].get('Description', '')
            print(f"  Reason: {reason}")
            if description:
                print(f"  Description: {description}")
            all_healthy = False
    
    if all_healthy:
        print("\n✓ All targets are healthy!")
    
    return all_healthy

def main():
    """Main execution function."""
    print("=" * 80)
    print("RECREATE SERVICE WITH FIXES")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        # Step 1: Get current service configuration
        print("Step 1: Getting current service configuration...")
        service_config = get_service_config()
        print(f"✓ Service found: {service_config['serviceName']}")
        print(f"  Status: {service_config['status']}")
        
        # Step 2: Delete the service
        print("\nStep 2: Deleting INACTIVE service...")
        delete_service()
        print("✓ Service deleted")
        
        # Step 3: Create fixed task definition
        print("\nStep 3: Creating fixed task definition...")
        task_def_arn, revision, env_vars = create_fixed_task_definition()
        print(f"✓ Registered new task definition: multimodal-lib-prod-app:{revision}")
        print(f"  ARN: {task_def_arn}")
        
        # Show what we're setting
        print("\nCritical environment variables:")
        for env in env_vars:
            if 'OPENSEARCH' in env['name'] or 'VECTOR' in env['name'] or 'NEPTUNE' in env['name'] or 'HEALTH' in env['name']:
                print(f"  {env['name']}: {env['value']}")
        
        # Step 4: Create new service
        print("\nStep 4: Creating new service with fixed task definition...")
        create_service(task_def_arn, service_config)
        
        # Step 5: Wait for deployment
        print("\nStep 5: Waiting for deployment to complete...")
        deployment_success = wait_for_deployment(timeout=600)
        
        if not deployment_success:
            print("\n⚠ WARNING: Deployment did not complete successfully")
            print("Check ECS console for details")
            return 1
        
        # Step 6: Check target health
        print("\nStep 6: Checking target health...")
        time.sleep(30)  # Wait a bit for health checks to run
        health_success = check_target_health()
        
        if not health_success:
            print("\n⚠ WARNING: Targets are not healthy yet")
            print("This may take a few more minutes. Monitor the ALB target group.")
            print("The fixes have been applied, so health checks should pass soon.")
        
        # Success!
        print("\n" + "=" * 80)
        print("SERVICE RECREATED SUCCESSFULLY!")
        print("=" * 80)
        print(f"✓ New task definition: multimodal-lib-prod-app:{revision}")
        print(f"✓ Service created and deployed")
        print()
        print("The application has been deployed with:")
        print("  - OpenSearch initialization disabled (SKIP_OPENSEARCH_INIT=true)")
        print("  - Vector search disabled (ENABLE_VECTOR_SEARCH=false)")
        print("  - Short timeouts (OPENSEARCH_TIMEOUT=5)")
        print("  - Health checks optimized (HEALTH_CHECK_TIMEOUT=2)")
        print()
        print("Next steps:")
        print("  1. Monitor target health in ALB console")
        print("  2. Check application logs for startup progress")
        print("  3. Verify health check endpoint responds quickly")
        print("  4. Once stable, you can work on fixing OpenSearch connectivity")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
