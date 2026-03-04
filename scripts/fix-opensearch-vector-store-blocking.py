#!/usr/bin/env python3
"""
Fix OpenSearch and Vector Store Blocking Issues

This script fixes the critical issues preventing application stabilization:
1. OpenSearch initialization blocking health checks (60s timeout)
2. Vector store initialization errors causing health check failures

Root Causes:
- Health check endpoint waits for OpenSearch to initialize (60s connection timeout)
- Vector store is disabled but code still tries to initialize it
- EnhancedSemanticSearchService requires vector_store argument but it's not provided

Solution:
- Disable vector search and OpenSearch initialization via environment variables
- Set short timeouts for any attempted connections
- Ensure health check responds immediately without waiting for dependencies
"""

import boto3
import json
import time
from datetime import datetime

def get_current_task_definition():
    """Get the current task definition."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # Get current service
    service_response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service']
    )
    
    if not service_response['services']:
        raise Exception("Service not found")
    
    task_def_arn = service_response['services'][0]['taskDefinition']
    task_def_name = task_def_arn.split('/')[-1]
    
    # Get task definition
    task_def_response = ecs.describe_task_definition(taskDefinition=task_def_name)
    return task_def_response['taskDefinition']

def create_fixed_task_definition(current_task_def):
    """Create a new task definition with OpenSearch and vector store disabled."""
    
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
    
    return new_task_def

def register_and_update_service(new_task_def):
    """Register new task definition and update service."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("REGISTERING NEW TASK DEFINITION")
    print("=" * 80)
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    new_revision = response['taskDefinition']['revision']
    
    print(f"✓ Registered new task definition: {new_task_def['family']}:{new_revision}")
    print(f"  ARN: {new_task_def_arn}")
    
    # Update service
    print("\n" + "=" * 80)
    print("UPDATING SERVICE")
    print("=" * 80)
    
    update_response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"✓ Service updated to use new task definition")
    print(f"  Deployment ID: {update_response['service']['deployments'][0]['id']}")
    
    return new_task_def_arn, new_revision

def wait_for_deployment(timeout=600):
    """Wait for deployment to complete."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("WAITING FOR DEPLOYMENT")
    print("=" * 80)
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        response = ecs.describe_services(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service']
        )
        
        service = response['services'][0]
        deployments = service['deployments']
        
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            running_count = deployments[0]['runningCount']
            desired_count = deployments[0]['desiredCount']
            
            status = f"Running: {running_count}/{desired_count}"
            if status != last_status:
                print(f"  {status}")
                last_status = status
            
            if running_count == desired_count and running_count > 0:
                print("\n✓ Deployment completed successfully!")
                return True
        else:
            status = f"Deployments: {len(deployments)}"
            if status != last_status:
                print(f"  {status}")
                for i, dep in enumerate(deployments):
                    print(f"    {i+1}. Status: {dep['status']}, Running: {dep['runningCount']}/{dep['desiredCount']}")
                last_status = status
        
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
            return False
    
    print("\n✓ All targets are healthy!")
    return True

def main():
    """Main execution function."""
    print("=" * 80)
    print("FIX OPENSEARCH AND VECTOR STORE BLOCKING ISSUES")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        # Step 1: Get current task definition
        print("Step 1: Getting current task definition...")
        current_task_def = get_current_task_definition()
        current_family = current_task_def['family']
        current_revision = current_task_def['revision']
        print(f"✓ Current task definition: {current_family}:{current_revision}")
        
        # Step 2: Create fixed task definition
        print("\nStep 2: Creating fixed task definition...")
        new_task_def = create_fixed_task_definition(current_task_def)
        
        # Show what we're changing
        print("\nEnvironment variables being set:")
        container_def = new_task_def['containerDefinitions'][0]
        for env in container_def['environment']:
            if 'OPENSEARCH' in env['name'] or 'VECTOR' in env['name'] or 'NEPTUNE' in env['name'] or 'HEALTH' in env['name']:
                print(f"  {env['name']}: {env['value']}")
        
        # Step 3: Register and update
        print("\nStep 3: Registering new task definition and updating service...")
        new_task_def_arn, new_revision = register_and_update_service(new_task_def)
        
        # Step 4: Wait for deployment
        print("\nStep 4: Waiting for deployment to complete...")
        deployment_success = wait_for_deployment(timeout=600)
        
        if not deployment_success:
            print("\n⚠ WARNING: Deployment did not complete successfully")
            print("Check ECS console for details")
            return 1
        
        # Step 5: Check target health
        print("\nStep 5: Checking target health...")
        time.sleep(30)  # Wait a bit for health checks to run
        health_success = check_target_health()
        
        if not health_success:
            print("\n⚠ WARNING: Targets are not healthy yet")
            print("This may take a few more minutes. Monitor the ALB target group.")
            return 1
        
        # Success!
        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)
        print(f"✓ New task definition: {current_family}:{new_revision}")
        print(f"✓ Service updated and deployed")
        print(f"✓ All targets healthy")
        print()
        print("The application should now be stable with:")
        print("  - OpenSearch initialization disabled")
        print("  - Vector search disabled")
        print("  - Health checks responding immediately")
        print()
        print("Next steps:")
        print("  1. Verify application is accessible via ALB")
        print("  2. Check application logs for any errors")
        print("  3. Once stable, you can work on fixing OpenSearch connectivity")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit(main())
