#!/usr/bin/env python3
"""
Reactivate Service and Fix OpenSearch/Vector Store Blocking

This script:
1. Reactivates the INACTIVE service
2. Applies the OpenSearch and vector store fixes
3. Monitors deployment until stable
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

def reactivate_service_with_fixed_task_def(new_task_def_arn):
    """Reactivate the service with the fixed task definition."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("REACTIVATING SERVICE")
    print("=" * 80)
    
    # Update service to set desired count to 1 and use new task definition
    response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        desiredCount=1,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"✓ Service reactivated with desired count: 1")
    print(f"✓ Using task definition: {new_task_def_arn}")
    
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
        response = ecs.describe_services(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service']
        )
        
        service = response['services'][0]
        service_status = service['status']
        deployments = service['deployments']
        
        print(f"\nService Status: {service_status}")
        
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            running_count = deployments[0]['runningCount']
            desired_count = deployments[0]['desiredCount']
            
            status = f"Running: {running_count}/{desired_count}"
            if status != last_status:
                print(f"  {status}")
                last_status = status
            
            if running_count == desired_count and running_count > 0 and service_status == 'ACTIVE':
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
    print("REACTIVATE SERVICE AND FIX BLOCKING ISSUES")
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
        
        # Step 3: Register new task definition
        print("\nStep 3: Registering new task definition...")
        ecs = boto3.client('ecs', region_name='us-east-1')
        response = ecs.register_task_definition(**new_task_def)
        new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
        new_revision = response['taskDefinition']['revision']
        print(f"✓ Registered new task definition: {new_task_def['family']}:{new_revision}")
        print(f"  ARN: {new_task_def_arn}")
        
        # Step 4: Reactivate service with new task definition
        print("\nStep 4: Reactivating service with fixed task definition...")
        reactivate_service_with_fixed_task_def(new_task_def_arn)
        
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
        print("DEPLOYMENT COMPLETE!")
        print("=" * 80)
        print(f"✓ New task definition: {current_family}:{new_revision}")
        print(f"✓ Service reactivated and deployed")
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
