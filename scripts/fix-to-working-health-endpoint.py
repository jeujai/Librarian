#!/usr/bin/env python3
"""
Fix to Working Health Endpoint

Based on the logs, the application successfully responds to /health.
This script creates a new task definition with the correct /health endpoint.
"""

import json
import boto3
import sys
from datetime import datetime

def fix_to_working_endpoint():
    """Create task definition with /health endpoint that actually works."""
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    print("=" * 80)
    print("FIXING TO WORKING HEALTH ENDPOINT")
    print("=" * 80)
    print()
    
    # Get task definition #16 as base
    print("1. Getting base task definition...")
    response = ecs.describe_task_definition(
        taskDefinition='multimodal-lib-prod-app:16'
    )
    
    task_def = response['taskDefinition']
    print(f"   Base: {task_def['family']}:{task_def['revision']}")
    print(f"   Current health check: {task_def['containerDefinitions'][0]['healthCheck']['command']}")
    print()
    
    # Update health check to /health (which we know works from logs)
    print("2. Updating health check to /health...")
    task_def['containerDefinitions'][0]['healthCheck']['command'] = [
        "CMD-SHELL",
        "curl -f http://localhost:8000/health || exit 1"
    ]
    
    # Also increase the start period to give more time
    task_def['containerDefinitions'][0]['healthCheck']['startPeriod'] = 180  # 3 minutes
    
    # Remove fields that can't be used in register_task_definition
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'compatibilities', 'registeredAt', 'registeredBy'
    ]
    for field in fields_to_remove:
        task_def.pop(field, None)
    
    print("   New health check: curl -f http://localhost:8000/health || exit 1")
    print("   Start period: 180 seconds")
    print()
    
    # Register new task definition
    print("3. Registering new task definition...")
    new_task_def = ecs.register_task_definition(**task_def)
    new_revision = new_task_def['taskDefinition']['revision']
    print(f"   New task definition: {task_def['family']}:{new_revision}")
    print()
    
    # Update load balancer health check
    print("4. Updating load balancer health check...")
    elbv2.modify_target_group(
        TargetGroupArn='arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773',
        HealthCheckPath='/health'
    )
    print("   Load balancer health check: /health")
    print()
    
    # Update service
    print("5. Updating service...")
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
        "action": "fix_health_endpoint",
        "base_task_definition": "multimodal-lib-prod-app:16",
        "new_task_definition": f"{task_def['family']}:{new_revision}",
        "health_check_endpoint": "/health",
        "health_check_start_period": 180,
        "load_balancer_health_check": "/health",
        "status": "deployed"
    }
    
    output_file = f"health-endpoint-fix-{int(datetime.now().timestamp())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print()
    print("=" * 80)
    print("HEALTH ENDPOINT FIX DEPLOYED")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Created task definition revision {new_revision}")
    print(f"  - Health check endpoint: /health (verified working from logs)")
    print(f"  - Start period: 180 seconds (3 minutes)")
    print(f"  - Load balancer health check: /health")
    print()
    print("This configuration matches what was working in the logs:")
    print("  INFO: 10.0.0.188:18420 - 'GET /health HTTP/1.1' 200 OK")
    print()
    print("Next steps:")
    print("  1. Wait for task to start (2-3 minutes)")
    print("  2. Monitor health status")
    print("  3. Verify task becomes healthy")
    print()
    
    return results

if __name__ == "__main__":
    try:
        results = fix_to_working_endpoint()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
