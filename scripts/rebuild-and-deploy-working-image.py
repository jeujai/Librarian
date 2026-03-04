#!/usr/bin/env python3
"""
Rebuild and Deploy Working Image

The ECR repository is empty, which is why all deployments are failing.
This script rebuilds the Docker image and deploys it.
"""

import json
import subprocess
import boto3
import sys
from datetime import datetime

def run_command(cmd, description):
    """Run a shell command and handle errors."""
    print(f"\n{description}...")
    print(f"Command: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: {description} failed")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        return False
    
    print(f"SUCCESS: {description} completed")
    if result.stdout:
        print(f"Output: {result.stdout[:500]}")
    return True

def rebuild_and_deploy():
    """Rebuild Docker image and deploy to ECS."""
    
    print("=" * 80)
    print("REBUILDING AND DEPLOYING WORKING IMAGE")
    print("=" * 80)
    print()
    
    # Configuration
    region = 'us-east-1'
    account_id = '591222106065'
    repository = 'multimodal-lib-prod-app'
    image_tag = datetime.now().strftime('%Y%m%d-%H%M%S')
    image_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repository}:{image_tag}"
    
    print(f"Configuration:")
    print(f"  Region: {region}")
    print(f"  Repository: {repository}")
    print(f"  Image Tag: {image_tag}")
    print(f"  Image URI: {image_uri}")
    print()
    
    # Step 1: Login to ECR
    if not run_command(
        f"aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{region}.amazonaws.com",
        "1. Logging in to ECR"
    ):
        return False
    
    # Step 2: Build Docker image
    if not run_command(
        f"docker build -t {repository}:{image_tag} -f Dockerfile .",
        "2. Building Docker image"
    ):
        return False
    
    # Step 3: Tag image for ECR
    if not run_command(
        f"docker tag {repository}:{image_tag} {image_uri}",
        "3. Tagging image for ECR"
    ):
        return False
    
    # Step 4: Push image to ECR
    if not run_command(
        f"docker push {image_uri}",
        "4. Pushing image to ECR"
    ):
        return False
    
    # Step 5: Create new task definition
    print("\n5. Creating new task definition...")
    ecs = boto3.client('ecs', region_name=region)
    
    # Get base task definition
    response = ecs.describe_task_definition(
        taskDefinition='multimodal-lib-prod-app:16'
    )
    
    task_def = response['taskDefinition']
    
    # Update image URI
    task_def['containerDefinitions'][0]['image'] = image_uri
    
    # Update health check to /health
    task_def['containerDefinitions'][0]['healthCheck'] = {
        'command': ['CMD-SHELL', 'curl -f http://localhost:8000/health || exit 1'],
        'interval': 30,
        'timeout': 15,
        'retries': 5,
        'startPeriod': 180
    }
    
    # Remove fields that can't be used in register_task_definition
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'compatibilities', 'registeredAt', 'registeredBy'
    ]
    for field in fields_to_remove:
        task_def.pop(field, None)
    
    # Register new task definition
    new_task_def = ecs.register_task_definition(**task_def)
    new_revision = new_task_def['taskDefinition']['revision']
    print(f"   New task definition: {task_def['family']}:{new_revision}")
    print(f"   Image: {image_uri}")
    print()
    
    # Step 6: Update load balancer health check
    print("6. Updating load balancer health check...")
    elbv2 = boto3.client('elbv2', region_name=region)
    elbv2.modify_target_group(
        TargetGroupArn='arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773',
        HealthCheckPath='/health'
    )
    print("   Health check path: /health")
    print()
    
    # Step 7: Update service
    print("7. Updating service...")
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
        "action": "rebuild_and_deploy",
        "docker_image": image_uri,
        "image_tag": image_tag,
        "task_definition": f"{task_def['family']}:{new_revision}",
        "health_check_endpoint": "/health",
        "health_check_start_period": 180,
        "status": "deployed"
    }
    
    output_file = f"rebuild-deploy-{int(datetime.now().timestamp())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print()
    print("=" * 80)
    print("REBUILD AND DEPLOY COMPLETE")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Built and pushed Docker image: {image_tag}")
    print(f"  - Created task definition revision: {new_revision}")
    print(f"  - Health check endpoint: /health")
    print(f"  - Service deployment initiated")
    print()
    print("Next steps:")
    print("  1. Wait for task to start (3-5 minutes)")
    print("  2. Monitor task health status")
    print("  3. Verify application is accessible")
    print()
    print("Monitoring commands:")
    print(f"  # Check service status")
    print(f"  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service --region {region}")
    print()
    print(f"  # Check task health")
    print(f"  aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773 --region {region}")
    print()
    
    return True

if __name__ == "__main__":
    try:
        success = rebuild_and_deploy()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
