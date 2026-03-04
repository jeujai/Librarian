#!/usr/bin/env python3
"""
Fix Health Check Endpoint

This script updates the ECS task definition to use the correct health check endpoint.
The application is responding to /health but the task definition is checking /api/health/minimal.
"""

import json
import boto3
import sys
from datetime import datetime

def fix_health_check_endpoint():
    """Update task definition with correct health check endpoint."""
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("FIXING HEALTH CHECK ENDPOINT")
    print("=" * 80)
    print()
    
    # Get current task definition
    print("1. Getting current task definition...")
    response = ecs.describe_task_definition(
        taskDefinition='multimodal-lib-prod-app:17'
    )
    
    task_def = response['taskDefinition']
    print(f"   Current task definition: {task_def['family']}:{task_def['revision']}")
    print(f"   Current health check: {task_def['containerDefinitions'][0]['healthCheck']['command']}")
    print()
    
    # Update health check command
    print("2. Updating health check command...")
    task_def['containerDefinitions'][0]['healthCheck']['command'] = [
        "CMD-SHELL",
        "curl -f http://localhost:8000/health || exit 1"
    ]
    
    # Remove fields that can't be used in register_task_definition
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'compatibilities', 'registeredAt', 'registeredBy'
    ]
    for field in fields_to_remove:
        task_def.pop(field, None)
    
    print("   New health check: curl -f http://localhost:8000/health || exit 1")
    print()
    
    # Register new task definition
    print("3. Registering new task definition...")
    new_task_def = ecs.register_task_definition(**task_def)
    new_revision = new_task_def['taskDefinition']['revision']
    print(f"   New task definition: {task_def['family']}:{new_revision}")
    print()
    
    # Update service to use new task definition
    print("4. Updating service...")
    ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=f"{task_def['family']}:{new_revision}",
        forceNewDeployment=True
    )
    print("   Service updated successfully")
    print()
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "old_task_definition": f"{task_def['family']}:17",
        "new_task_definition": f"{task_def['family']}:{new_revision}",
        "old_health_check": "curl -f http://localhost:8000/api/health/minimal || exit 1",
        "new_health_check": "curl -f http://localhost:8000/health || exit 1",
        "load_balancer_health_check": "/health",
        "status": "success"
    }
    
    output_file = f"health-check-fix-{int(datetime.now().timestamp())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print()
    print("=" * 80)
    print("HEALTH CHECK FIX COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Updated task definition from revision 17 to {new_revision}")
    print(f"  - Changed health check endpoint from /api/health/minimal to /health")
    print(f"  - Load balancer health check already updated to /health")
    print(f"  - Service will redeploy with new task definition")
    print()
    print("Next steps:")
    print("  1. Wait for new task to start (2-3 minutes)")
    print("  2. Monitor health check status")
    print("  3. Verify task becomes healthy")
    print()
    
    return results

if __name__ == "__main__":
    try:
        results = fix_health_check_endpoint()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
