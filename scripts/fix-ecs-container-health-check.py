#!/usr/bin/env python3
"""
Fix ECS Container Health Check

This script updates the ECS task definition to use /health/simple instead of
/health/minimal for the container health check. This prevents containers from
being killed during startup when MinimalServer.health_check_ready is False.

Root Cause:
- Container health check uses /health/minimal which returns 503 during startup
- ALB health check uses /health/simple which always returns 200
- This mismatch causes ECS to kill containers before they fully initialize

Fix:
- Change container health check to use /health/simple (same as ALB)
- Container will pass health checks as soon as HTTP server is listening
"""

import boto3
import json
import sys
import time
from datetime import datetime

# Configuration
AWS_REGION = "us-east-1"
ECS_CLUSTER = "multimodal-lib-prod-cluster"
ECS_SERVICE = "multimodal-lib-prod-service-alb"

def get_current_task_definition():
    """Get the current task definition from the ECS service."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    # Get current service
    response = ecs.describe_services(
        cluster=ECS_CLUSTER,
        services=[ECS_SERVICE]
    )
    
    if not response['services']:
        print("ERROR: Service not found")
        return None
    
    task_def_arn = response['services'][0]['taskDefinition']
    print(f"Current task definition: {task_def_arn}")
    
    # Get task definition details
    response = ecs.describe_task_definition(taskDefinition=task_def_arn)
    return response['taskDefinition']

def update_health_check(task_def):
    """Update the health check command in the task definition."""
    container_defs = task_def['containerDefinitions']
    
    for container in container_defs:
        if container['name'] == 'multimodal-librarian':
            current_health_check = container.get('healthCheck', {})
            current_command = current_health_check.get('command', [])
            
            print(f"\nCurrent health check:")
            print(f"  Command: {current_command}")
            print(f"  Interval: {current_health_check.get('interval', 'N/A')}s")
            print(f"  Timeout: {current_health_check.get('timeout', 'N/A')}s")
            print(f"  Retries: {current_health_check.get('retries', 'N/A')}")
            print(f"  Start Period: {current_health_check.get('startPeriod', 'N/A')}s")
            
            # Update health check to use /health/simple
            new_health_check = {
                "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/simple || exit 1"],
                "interval": 30,
                "timeout": 15,
                "retries": 5,
                "startPeriod": 300
            }
            
            container['healthCheck'] = new_health_check
            
            print(f"\nNew health check:")
            print(f"  Command: {new_health_check['command']}")
            print(f"  Interval: {new_health_check['interval']}s")
            print(f"  Timeout: {new_health_check['timeout']}s")
            print(f"  Retries: {new_health_check['retries']}")
            print(f"  Start Period: {new_health_check['startPeriod']}s")
            
            return True
    
    print("ERROR: Container 'multimodal-librarian' not found")
    return False

def register_new_task_definition(task_def):
    """Register a new task definition with the updated health check."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    # Prepare registration parameters
    register_params = {
        'family': task_def['family'],
        'containerDefinitions': task_def['containerDefinitions'],
        'requiresCompatibilities': task_def.get('requiresCompatibilities', ['FARGATE']),
        'networkMode': task_def.get('networkMode', 'awsvpc'),
        'cpu': task_def.get('cpu', '4096'),
        'memory': task_def.get('memory', '8192'),
    }
    
    # Add optional parameters if present
    if task_def.get('taskRoleArn'):
        register_params['taskRoleArn'] = task_def['taskRoleArn']
    if task_def.get('executionRoleArn'):
        register_params['executionRoleArn'] = task_def['executionRoleArn']
    if task_def.get('ephemeralStorage'):
        register_params['ephemeralStorage'] = task_def['ephemeralStorage']
    if task_def.get('runtimePlatform'):
        register_params['runtimePlatform'] = task_def['runtimePlatform']
    
    # Register new task definition
    response = ecs.register_task_definition(**register_params)
    
    new_task_def = response['taskDefinition']
    new_arn = new_task_def['taskDefinitionArn']
    revision = new_task_def['revision']
    
    print(f"\nRegistered new task definition:")
    print(f"  ARN: {new_arn}")
    print(f"  Revision: {revision}")
    
    return new_arn

def update_service(task_def_arn):
    """Update the ECS service with the new task definition."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    print(f"\nUpdating service {ECS_SERVICE}...")
    
    response = ecs.update_service(
        cluster=ECS_CLUSTER,
        service=ECS_SERVICE,
        taskDefinition=task_def_arn,
        forceNewDeployment=True
    )
    
    print("Service update initiated")
    return response

def wait_for_deployment(timeout_minutes=15):
    """Wait for the deployment to complete."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    print(f"\nWaiting for deployment (timeout: {timeout_minutes} minutes)...")
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        response = ecs.describe_services(
            cluster=ECS_CLUSTER,
            services=[ECS_SERVICE]
        )
        
        if not response['services']:
            print("ERROR: Service not found")
            return False
        
        service = response['services'][0]
        deployments = service.get('deployments', [])
        
        primary_deployments = [d for d in deployments if d['status'] == 'PRIMARY']
        active_deployments = [d for d in deployments if d['status'] == 'ACTIVE']
        
        if primary_deployments:
            primary = primary_deployments[0]
            running = primary.get('runningCount', 0)
            desired = primary.get('desiredCount', 1)
            
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed}s] Primary: {running}/{desired} running, Active deployments: {len(active_deployments)}")
            
            if running >= desired and len(active_deployments) == 0:
                print("\n✅ Deployment completed successfully!")
                return True
        
        time.sleep(15)
    
    print(f"\n⚠️ Deployment timed out after {timeout_minutes} minutes")
    return False

def check_target_health():
    """Check ALB target group health."""
    elbv2 = boto3.client('elbv2', region_name=AWS_REGION)
    
    # Find target group
    response = elbv2.describe_target_groups()
    target_group = None
    
    for tg in response['TargetGroups']:
        if 'multimodal-lib-prod' in tg['TargetGroupName']:
            target_group = tg
            break
    
    if not target_group:
        print("Target group not found")
        return
    
    # Check health
    response = elbv2.describe_target_health(
        TargetGroupArn=target_group['TargetGroupArn']
    )
    
    print(f"\nTarget Group Health:")
    print(f"  Name: {target_group['TargetGroupName']}")
    print(f"  Health Check Path: {target_group.get('HealthCheckPath', 'N/A')}")
    
    for target in response['TargetHealthDescriptions']:
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', '')
        
        status_icon = "✅" if state == "healthy" else "❌" if state == "unhealthy" else "⏳"
        print(f"  {status_icon} Target: {target['Target']['Id']} - {state}")
        if reason:
            print(f"      Reason: {reason}")

def main():
    """Main function to fix the ECS container health check."""
    print("=" * 60)
    print("FIX ECS CONTAINER HEALTH CHECK")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Cluster: {ECS_CLUSTER}")
    print(f"Service: {ECS_SERVICE}")
    print()
    print("This script changes the container health check from:")
    print("  /health/minimal (returns 503 during startup)")
    print("To:")
    print("  /health/simple (always returns 200)")
    print()
    
    # Step 1: Get current task definition
    print("=" * 60)
    print("STEP 1: Get Current Task Definition")
    print("=" * 60)
    
    task_def = get_current_task_definition()
    if not task_def:
        sys.exit(1)
    
    # Step 2: Update health check
    print("\n" + "=" * 60)
    print("STEP 2: Update Health Check Configuration")
    print("=" * 60)
    
    if not update_health_check(task_def):
        sys.exit(1)
    
    # Step 3: Register new task definition
    print("\n" + "=" * 60)
    print("STEP 3: Register New Task Definition")
    print("=" * 60)
    
    new_task_def_arn = register_new_task_definition(task_def)
    if not new_task_def_arn:
        sys.exit(1)
    
    # Step 4: Update service
    print("\n" + "=" * 60)
    print("STEP 4: Update ECS Service")
    print("=" * 60)
    
    update_service(new_task_def_arn)
    
    # Step 5: Wait for deployment
    print("\n" + "=" * 60)
    print("STEP 5: Wait for Deployment")
    print("=" * 60)
    
    success = wait_for_deployment(timeout_minutes=15)
    
    # Step 6: Check target health
    print("\n" + "=" * 60)
    print("STEP 6: Check Target Health")
    print("=" * 60)
    
    check_target_health()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"New Task Definition: {new_task_def_arn}")
    print(f"Health Check: /health/simple")
    print(f"Deployment Status: {'SUCCESS' if success else 'IN PROGRESS'}")
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "task_definition": new_task_def_arn,
        "health_check_endpoint": "/health/simple",
        "deployment_success": success,
        "fix_description": "Changed container health check from /health/minimal to /health/simple"
    }
    
    output_file = f"ecs-health-check-fix-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")
    
    if not success:
        print("\n⚠️ Deployment may still be in progress. Monitor with:")
        print(f"  aws ecs describe-services --cluster {ECS_CLUSTER} --services {ECS_SERVICE}")

if __name__ == "__main__":
    main()
