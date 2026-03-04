#!/usr/bin/env python3
"""
Deploy fix for lazy ML model loading to prevent health check timeouts.

This script deploys the fix that makes ML model loading lazy in:
- CrossEncoderReranker (cross-encoder model)
- EntityExtractor (spaCy NLP model)
- IntentClassifier (transformers pipeline)

These models were being loaded synchronously during service initialization,
blocking the event loop and causing health check timeouts.

V3 Changes:
- Added 2-minute delay to ServiceHealthMonitor._background_monitoring()
- Fixed VectorStoreHealthCheck to check cache directly instead of calling get_vector_store_optional()
- Both HealthCheckSystem and ServiceHealthMonitor now wait 2 minutes before running health checks
- Health checks no longer trigger service creation during startup

V2 Changes:
- Made imports of sentence_transformers, spacy, and transformers lazy
- Added 2-minute delay before background health monitoring starts in HealthCheckSystem
"""

import boto3
import json
import subprocess
import sys
import time
from datetime import datetime

# Configuration
AWS_REGION = "us-east-1"
ECR_REPOSITORY = "multimodal-librarian"
ECS_CLUSTER = "multimodal-lib-prod-cluster"
ECS_SERVICE = "multimodal-lib-prod-service-alb"
IMAGE_TAG = "lazy-ml-models-v4"

def run_command(cmd, description):
    """Run a shell command and return output."""
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {description}")
    print(f"Command: {cmd}")
    print('='*60)
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    
    if result.returncode != 0:
        print(f"ERROR: Command failed with return code {result.returncode}")
        return None
    
    return result.stdout.strip()

def get_aws_account_id():
    """Get AWS account ID."""
    sts = boto3.client('sts', region_name=AWS_REGION)
    return sts.get_caller_identity()['Account']

def build_and_push_image(account_id):
    """Build Docker image and push to ECR."""
    ecr_uri = f"{account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com/{ECR_REPOSITORY}"
    full_image = f"{ecr_uri}:{IMAGE_TAG}"
    
    # Login to ECR
    login_cmd = f"aws ecr get-login-password --region {AWS_REGION} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com"
    if run_command(login_cmd, "Logging into ECR") is None:
        return None
    
    # Build image
    build_cmd = f"docker build -t {full_image} ."
    if run_command(build_cmd, "Building Docker image with lazy ML model loading fix") is None:
        return None
    
    # Push image
    push_cmd = f"docker push {full_image}"
    if run_command(push_cmd, "Pushing image to ECR") is None:
        return None
    
    return full_image

def get_current_task_definition():
    """Get the current task definition."""
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
    
    # Get task definition details
    response = ecs.describe_task_definition(taskDefinition=task_def_arn)
    return response['taskDefinition']

def create_new_task_definition(current_task_def, new_image):
    """Create a new task definition with the updated image."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    # Update container image
    container_defs = current_task_def['containerDefinitions']
    for container in container_defs:
        if container['name'] == 'multimodal-librarian':
            container['image'] = new_image
            print(f"Updated container image to: {new_image}")
    
    # Register new task definition
    response = ecs.register_task_definition(
        family=current_task_def['family'],
        taskRoleArn=current_task_def.get('taskRoleArn', ''),
        executionRoleArn=current_task_def.get('executionRoleArn', ''),
        networkMode=current_task_def.get('networkMode', 'awsvpc'),
        containerDefinitions=container_defs,
        requiresCompatibilities=current_task_def.get('requiresCompatibilities', ['FARGATE']),
        cpu=current_task_def.get('cpu', '4096'),
        memory=current_task_def.get('memory', '8192'),
        ephemeralStorage=current_task_def.get('ephemeralStorage', {'sizeInGiB': 30}),
        runtimePlatform=current_task_def.get('runtimePlatform', {
            'cpuArchitecture': 'X86_64',
            'operatingSystemFamily': 'LINUX'
        })
    )
    
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    revision = response['taskDefinition']['revision']
    print(f"Created new task definition: {new_task_def_arn} (revision {revision})")
    
    return new_task_def_arn

def update_service(task_def_arn):
    """Update ECS service with new task definition."""
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    response = ecs.update_service(
        cluster=ECS_CLUSTER,
        service=ECS_SERVICE,
        taskDefinition=task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"Service update initiated")
    return response

def wait_for_deployment(timeout_minutes=15):
    """Wait for deployment to complete."""
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
        
        # Check if there's only one deployment (meaning the new one is complete)
        primary_deployments = [d for d in deployments if d['status'] == 'PRIMARY']
        active_deployments = [d for d in deployments if d['status'] == 'ACTIVE']
        
        if primary_deployments:
            primary = primary_deployments[0]
            running = primary.get('runningCount', 0)
            desired = primary.get('desiredCount', 1)
            
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed}s] Primary deployment: {running}/{desired} tasks running, "
                  f"Active deployments: {len(active_deployments)}")
            
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
    
    print(f"\nTarget Group: {target_group['TargetGroupName']}")
    print(f"Health Check Path: {target_group.get('HealthCheckPath', 'N/A')}")
    print(f"Health Check Interval: {target_group.get('HealthCheckIntervalSeconds', 'N/A')}s")
    print(f"Healthy Threshold: {target_group.get('HealthyThresholdCount', 'N/A')}")
    
    for target in response['TargetHealthDescriptions']:
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', '')
        description = target['TargetHealth'].get('Description', '')
        
        status_icon = "✅" if state == "healthy" else "❌" if state == "unhealthy" else "⏳"
        print(f"  {status_icon} Target: {target['Target']['Id']} - {state}")
        if reason:
            print(f"      Reason: {reason}")
        if description:
            print(f"      Description: {description}")

def main():
    """Main deployment function."""
    print("="*60)
    print("DEPLOYING LAZY ML MODEL LOADING FIX")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Region: {AWS_REGION}")
    print(f"Cluster: {ECS_CLUSTER}")
    print(f"Service: {ECS_SERVICE}")
    print(f"Image Tag: {IMAGE_TAG}")
    
    # Get AWS account ID
    account_id = get_aws_account_id()
    print(f"Account ID: {account_id}")
    
    # Build and push image
    print("\n" + "="*60)
    print("STEP 1: Build and Push Docker Image")
    print("="*60)
    
    new_image = build_and_push_image(account_id)
    if not new_image:
        print("ERROR: Failed to build and push image")
        sys.exit(1)
    
    # Get current task definition
    print("\n" + "="*60)
    print("STEP 2: Get Current Task Definition")
    print("="*60)
    
    current_task_def = get_current_task_definition()
    if not current_task_def:
        print("ERROR: Failed to get current task definition")
        sys.exit(1)
    
    print(f"Current task definition: {current_task_def['taskDefinitionArn']}")
    
    # Create new task definition
    print("\n" + "="*60)
    print("STEP 3: Create New Task Definition")
    print("="*60)
    
    new_task_def_arn = create_new_task_definition(current_task_def, new_image)
    if not new_task_def_arn:
        print("ERROR: Failed to create new task definition")
        sys.exit(1)
    
    # Update service
    print("\n" + "="*60)
    print("STEP 4: Update ECS Service")
    print("="*60)
    
    update_service(new_task_def_arn)
    
    # Wait for deployment
    print("\n" + "="*60)
    print("STEP 5: Wait for Deployment")
    print("="*60)
    
    success = wait_for_deployment(timeout_minutes=15)
    
    # Check target health
    print("\n" + "="*60)
    print("STEP 6: Check Target Health")
    print("="*60)
    
    check_target_health()
    
    # Summary
    print("\n" + "="*60)
    print("DEPLOYMENT SUMMARY")
    print("="*60)
    print(f"New Image: {new_image}")
    print(f"New Task Definition: {new_task_def_arn}")
    print(f"Deployment Status: {'SUCCESS' if success else 'PENDING/FAILED'}")
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "image": new_image,
        "task_definition": new_task_def_arn,
        "deployment_success": success,
        "fix_description": "Lazy ML model loading to prevent health check timeouts"
    }
    
    output_file = f"lazy-ml-model-fix-deployment-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")
    
    if not success:
        print("\n⚠️ Deployment may still be in progress. Monitor with:")
        print(f"  aws ecs describe-services --cluster {ECS_CLUSTER} --services {ECS_SERVICE}")
        sys.exit(1)

if __name__ == "__main__":
    main()
