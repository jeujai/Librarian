#!/usr/bin/env python3
"""
Fix Health Check Path Mismatch

Amazon Q Root Cause Analysis identified:
- ALB Target Group health check: /health/simple on port 8000
- ECS Container health check: /api/health/simple on port 8000

This mismatch causes tasks to fail ALB health checks even though the container
health check passes. The container is listening on /health/simple but the
task definition is checking /api/health/simple.

Solution: Update task definition to use /health/simple (matching ALB)
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("HEALTH CHECK PATH MISMATCH FIX")
    print("=" * 80)
    print()
    
    print("🔍 Root Cause:")
    print("   ALB expects: /health/simple")
    print("   Container checks: /api/health/simple")
    print("   Result: Tasks fail ALB health checks and get killed")
    print()
    
    # Get current task definition
    print("📋 Fetching current task definition...")
    response = ecs.describe_task_definition(taskDefinition='multimodal-lib-prod-app')
    task_def = response['taskDefinition']
    
    print(f"   Current revision: {task_def['revision']}")
    print()
    
    # Show current health check
    container = task_def['containerDefinitions'][0]
    if 'healthCheck' in container:
        current_cmd = container['healthCheck']['command']
        print("🏥 Current container health check:")
        print(f"   Command: {' '.join(current_cmd)}")
        print()
    
    # Update health check command
    print("🔧 Updating health check path...")
    print("   OLD: CMD-SHELL, curl -f http://localhost:8000/api/health/simple || exit 1")
    print("   NEW: CMD-SHELL, curl -f http://localhost:8000/health/simple || exit 1")
    print()
    
    # Create new container definition with corrected health check
    new_container_def = container.copy()
    new_container_def['healthCheck'] = {
        'command': [
            'CMD-SHELL',
            'curl -f http://localhost:8000/health/simple || exit 1'
        ],
        'interval': 30,
        'timeout': 5,
        'retries': 3,
        'startPeriod': 60
    }
    
    print("✓ Health check path corrected to match ALB target group")
    print()
    
    # Register new task definition
    print("📝 Registering new task definition...")
    
    register_params = {
        'family': task_def['family'],
        'taskRoleArn': task_def['taskRoleArn'],
        'executionRoleArn': task_def['executionRoleArn'],
        'networkMode': task_def['networkMode'],
        'containerDefinitions': [new_container_def],
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory'],
    }
    
    # Add optional fields if they exist
    if 'volumes' in task_def:
        register_params['volumes'] = task_def['volumes']
    if 'placementConstraints' in task_def:
        register_params['placementConstraints'] = task_def['placementConstraints']
    
    new_task_def = ecs.register_task_definition(**register_params)
    new_revision = new_task_def['taskDefinition']['revision']
    
    print(f"   ✓ New task definition registered: revision {new_revision}")
    print()
    
    # Update the service to use the new task definition
    print("🚀 Updating ECS service to multimodal-lib-prod-service-alb...")
    ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service-alb',
        taskDefinition=f"multimodal-lib-prod-app:{new_revision}",
        forceNewDeployment=True
    )
    
    print("   ✓ Service updated with corrected health check")
    print()
    
    print("=" * 80)
    print("✅ SUCCESS")
    print("=" * 80)
    print()
    print("Health check path has been corrected to match ALB configuration.")
    print()
    print("What happens next:")
    print("1. ECS starts new tasks with corrected health check (revision {})".format(new_revision))
    print("2. Container health check passes: /health/simple")
    print("3. ALB health check passes: /health/simple")
    print("4. Tasks become healthy and start receiving traffic")
    print("5. Old unhealthy tasks are drained and stopped")
    print()
    print("Expected timeline:")
    print("- 1-2 minutes: New tasks start")
    print("- 2-3 minutes: Container health checks pass")
    print("- 3-4 minutes: ALB health checks pass")
    print("- 5-6 minutes: Tasks registered as healthy targets")
    print()
    print("Monitor deployment:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster \\")
    print("    --services multimodal-lib-prod-service-alb \\")
    print("    --query 'services[0].events[0:5]'")
    print()
    print("Check target health:")
    print("  aws elbv2 describe-target-health \\")
    print("    --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'issue': 'health_check_path_mismatch',
        'root_cause': 'ALB expects /health/simple but container checks /api/health/simple',
        'old_revision': task_def['revision'],
        'new_revision': new_revision,
        'old_health_check': container.get('healthCheck', {}).get('command', []),
        'new_health_check': new_container_def['healthCheck']['command'],
        'service': 'multimodal-lib-prod-service-alb',
        'cluster': 'multimodal-lib-prod-cluster',
        'alb_target_group': 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34'
    }
    
    filename = f"health-check-path-fix-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {filename}")
    print()

if __name__ == '__main__':
    main()
