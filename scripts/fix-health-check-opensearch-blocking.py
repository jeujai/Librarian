#!/usr/bin/env python3
"""
Fix Health Check OpenSearch Blocking Issue

This script fixes the health check timeout issue by ensuring OpenSearch
initialization doesn't block the health check endpoint.

The problem: Health check calls get_minimal_server() which blocks on OpenSearch
connection timeout (60s), causing ALB health checks to timeout and mark tasks unhealthy.

The solution: Make OpenSearch initialization non-blocking and ensure health check
responds immediately regardless of OpenSearch status.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("=" * 80)
    print("FIXING HEALTH CHECK OPENSEARCH BLOCKING ISSUE")
    print("=" * 80)
    print()
    
    ecs = boto3.client('ecs')
    
    # Get current task definition
    print("1. Getting current task definition...")
    response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )
    
    current_task_def_arn = response['services'][0]['taskDefinition']
    task_def_name = current_task_def_arn.split('/')[-1].split(':')[0]
    
    print(f"   Current task definition: {current_task_def_arn}")
    
    # Get task definition details
    task_def_response = ecs.describe_task_definition(
        taskDefinition=current_task_def_arn
    )
    
    task_def = task_def_response['taskDefinition']
    
    # Create new task definition with environment variables to disable OpenSearch
    print("\n2. Creating new task definition with OpenSearch disabled...")
    
    container_def = task_def['containerDefinitions'][0]
    
    # Get existing environment variables
    env_vars = {env['name']: env['value'] for env in container_def.get('environment', [])}
    
    # Add/update environment variables to disable OpenSearch and Neptune
    env_vars.update({
        'ENABLE_VECTOR_SEARCH': 'false',
        'ENABLE_GRAPH_DB': 'false',
        'SKIP_OPENSEARCH_INIT': 'true',
        'SKIP_NEPTUNE_INIT': 'true',
        'OPENSEARCH_TIMEOUT': '5',  # Reduce timeout to 5 seconds
        'HEALTH_CHECK_TIMEOUT': '2',  # Health check should respond in 2 seconds
    })
    
    # Convert back to list format
    new_env = [{'name': k, 'value': v} for k, v in env_vars.items()]
    container_def['environment'] = new_env
    
    # Register new task definition
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def.get('networkMode'),
        'containerDefinitions': [container_def],
        'volumes': task_def.get('volumes', []),
        'requiresCompatibilities': task_def.get('requiresCompatibilities', []),
        'cpu': task_def.get('cpu'),
        'memory': task_def.get('memory'),
    }
    
    # Remove None values
    new_task_def = {k: v for k, v in new_task_def.items() if v is not None}
    
    register_response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    new_revision = register_response['taskDefinition']['revision']
    
    print(f"   ✓ New task definition registered: {task_def_name}:{new_revision}")
    print(f"   ✓ ARN: {new_task_def_arn}")
    
    # Update service to use new task definition
    print("\n3. Updating service with new task definition...")
    
    update_response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service-alb',
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"   ✓ Service updated")
    print(f"   ✓ Deployment ID: {update_response['service']['deployments'][0]['id']}")
    
    # Wait for deployment to stabilize
    print("\n4. Waiting for deployment to stabilize...")
    print("   This may take 5-10 minutes...")
    
    waiter = ecs.get_waiter('services_stable')
    
    try:
        waiter.wait(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service-alb'],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 40  # 10 minutes
            }
        )
        print("   ✓ Deployment stabilized successfully!")
        
    except Exception as e:
        print(f"   ⚠️  Deployment did not stabilize within timeout: {e}")
        print("   Check service status manually")
    
    # Check final status
    print("\n5. Checking final service status...")
    
    final_response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )
    
    service = final_response['services'][0]
    
    print(f"   Service Status: {service['status']}")
    print(f"   Desired Count: {service['desiredCount']}")
    print(f"   Running Count: {service['runningCount']}")
    print(f"   Pending Count: {service['pendingCount']}")
    
    if service['runningCount'] == service['desiredCount']:
        print("   ✓ Service is stable!")
    else:
        print("   ⚠️  Service is still deploying")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'old_task_definition': current_task_def_arn,
        'new_task_definition': new_task_def_arn,
        'new_revision': new_revision,
        'environment_variables_added': {
            'ENABLE_VECTOR_SEARCH': 'false',
            'ENABLE_GRAPH_DB': 'false',
            'SKIP_OPENSEARCH_INIT': 'true',
            'SKIP_NEPTUNE_INIT': 'true',
            'OPENSEARCH_TIMEOUT': '5',
            'HEALTH_CHECK_TIMEOUT': '2',
        },
        'service_status': {
            'status': service['status'],
            'desired_count': service['desiredCount'],
            'running_count': service['runningCount'],
            'pending_count': service['pendingCount'],
        }
    }
    
    output_file = f"health-check-opensearch-fix-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Results saved to: {output_file}")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("1. Monitor the deployment:")
    print("   python scripts/check-service-stability.py")
    print()
    print("2. Check application logs:")
    print("   aws logs tail /ecs/multimodal-lib-prod-app --follow")
    print()
    print("3. Verify health check is passing:")
    print("   aws elbv2 describe-target-health --target-group-arn <arn>")
    print()
    print("4. Once stable, you can gradually re-enable features:")
    print("   - Set ENABLE_VECTOR_SEARCH=true")
    print("   - Set SKIP_OPENSEARCH_INIT=false")
    print("   - But first fix OpenSearch connectivity!")
    print()

if __name__ == '__main__':
    main()
