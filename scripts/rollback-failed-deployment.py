#!/usr/bin/env python3
"""
Rollback Failed Deployment

This script rolls back the failed startup optimization deployment to the previous working version.
"""

import json
import boto3
import sys
from datetime import datetime

def rollback_deployment():
    """Rollback to previous working task definition."""
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("ROLLING BACK FAILED DEPLOYMENT")
    print("=" * 80)
    print()
    
    # Get current service configuration
    print("1. Getting current service configuration...")
    response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service']
    )
    
    service = response['services'][0]
    current_task_def = service['taskDefinition']
    print(f"   Current task definition: {current_task_def}")
    print(f"   Running count: {service['runningCount']}")
    print(f"   Desired count: {service['desiredCount']}")
    print()
    
    # List recent task definitions to find previous working version
    print("2. Finding previous working task definition...")
    response = ecs.list_task_definitions(
        familyPrefix='multimodal-lib-prod-app',
        status='ACTIVE',
        sort='DESC',
        maxResults=10
    )
    
    task_defs = response['taskDefinitionArns']
    print(f"   Found {len(task_defs)} recent task definitions:")
    for i, td in enumerate(task_defs[:5]):
        revision = td.split(':')[-1]
        print(f"     {i+1}. {td.split('/')[-1]}")
    print()
    
    # Use task definition #16 (before startup optimization)
    # Task definitions #17 and #18 are the failed startup optimization versions
    rollback_task_def = 'multimodal-lib-prod-app:16'
    
    print(f"3. Rolling back to: {rollback_task_def}")
    print("   This is the version before startup optimization deployment")
    print()
    
    # Get the task definition details to verify
    response = ecs.describe_task_definition(
        taskDefinition=rollback_task_def
    )
    
    task_def = response['taskDefinition']
    health_check = task_def['containerDefinitions'][0].get('healthCheck', {})
    print(f"   Health check command: {health_check.get('command', 'None')}")
    print()
    
    # Update service to use rollback task definition
    print("4. Updating service...")
    response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=rollback_task_def,
        forceNewDeployment=True
    )
    
    print("   Service updated successfully")
    print()
    
    # Also update load balancer health check to match
    print("5. Verifying load balancer health check...")
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    response = elbv2.describe_target_groups(
        TargetGroupArns=[
            'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773'
        ]
    )
    
    tg = response['TargetGroups'][0]
    current_health_path = tg['HealthCheckPath']
    print(f"   Current health check path: {current_health_path}")
    
    # The /health endpoint should work with the rollback version
    if current_health_path != '/health':
        print(f"   Updating health check path to /health...")
        elbv2.modify_target_group(
            TargetGroupArn=tg['TargetGroupArn'],
            HealthCheckPath='/health'
        )
        print("   Health check path updated")
    else:
        print("   Health check path is already correct")
    print()
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "action": "rollback",
        "from_task_definition": current_task_def,
        "to_task_definition": rollback_task_def,
        "reason": "Failed health checks in startup optimization deployment",
        "cluster": "multimodal-lib-prod-cluster",
        "service": "multimodal-lib-prod-service",
        "health_check_path": "/health",
        "status": "initiated"
    }
    
    output_file = f"rollback-deployment-{int(datetime.now().timestamp())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print()
    print("=" * 80)
    print("ROLLBACK INITIATED")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Rolling back from {current_task_def.split('/')[-1]} to {rollback_task_def}")
    print(f"  - Health check path: /health")
    print(f"  - Service will redeploy with previous task definition")
    print()
    print("Next steps:")
    print("  1. Wait for new task to start (2-3 minutes)")
    print("  2. Monitor task health status")
    print("  3. Verify task becomes healthy and stays running")
    print("  4. Check application is accessible via load balancer")
    print()
    print("Monitoring commands:")
    print("  # Check service status")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service --region us-east-1")
    print()
    print("  # Check task health")
    print("  aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773 --region us-east-1")
    print()
    
    return results

if __name__ == "__main__":
    try:
        results = rollback_deployment()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
