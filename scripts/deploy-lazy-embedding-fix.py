#!/usr/bin/env python3
"""
Deploy fix for health check timeouts caused by SentenceTransformer blocking.

The Problem:
------------
During startup, the OpenSearch client's connect() method was loading the 
SentenceTransformer embedding model synchronously. Even though this was run
in a thread pool via asyncio.to_thread(), the CPU-intensive model loading
(~3-5 seconds) would starve the event loop of CPU time on single-core containers,
preventing health checks from being processed and causing ALB to mark targets
as unhealthy.

The Fix:
--------
The embedding model is now loaded lazily on first use (when generate_embedding()
is called) rather than during connect(). This allows:
1. OpenSearch connection to complete quickly
2. Health checks to pass immediately
3. Embedding model to load in the background when first needed

This script rebuilds the Docker image with the fix and deploys it to ECS.
"""

import boto3
import subprocess
import json
import time
from datetime import datetime

# Configuration
AWS_REGION = "us-east-1"
ECR_REPOSITORY = "multimodal-librarian"
ECS_CLUSTER = "multimodal-lib-prod-cluster"
ECS_SERVICE = "multimodal-lib-prod-service-alb"
TASK_FAMILY = "multimodal-lib-prod-app"


def run_command(cmd: list, cwd: str = None) -> tuple:
    """Run a shell command and return output."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr


def get_ecr_login():
    """Get ECR login credentials."""
    ecr = boto3.client('ecr', region_name=AWS_REGION)
    response = ecr.get_authorization_token()
    auth_data = response['authorizationData'][0]
    return auth_data['authorizationToken'], auth_data['proxyEndpoint']


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 70)
    print("DEPLOYING LAZY EMBEDDING MODEL FIX")
    print("=" * 70)
    print(f"Timestamp: {timestamp}")
    print()
    
    # Get AWS account ID
    sts = boto3.client('sts', region_name=AWS_REGION)
    account_id = sts.get_caller_identity()['Account']
    ecr_uri = f"{account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com/{ECR_REPOSITORY}"
    
    print(f"ECR Repository: {ecr_uri}")
    print()
    
    # Step 1: Login to ECR
    print("Step 1: Logging in to ECR...")
    ecr = boto3.client('ecr', region_name=AWS_REGION)
    token_response = ecr.get_authorization_token()
    auth_data = token_response['authorizationData'][0]
    
    # Docker login
    registry = auth_data['proxyEndpoint']
    returncode, stdout, stderr = run_command([
        'docker', 'login', '--username', 'AWS', '--password-stdin', registry
    ])
    
    if returncode != 0:
        # Try alternative login method
        import base64
        token = base64.b64decode(auth_data['authorizationToken']).decode('utf-8')
        password = token.split(':')[1]
        
        process = subprocess.Popen(
            ['docker', 'login', '--username', 'AWS', '--password-stdin', registry],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=password)
        if process.returncode != 0:
            print(f"ECR login failed: {stderr}")
            return
    
    print("   ECR login successful")
    
    # Step 2: Build Docker image
    print("\nStep 2: Building Docker image with lazy embedding fix...")
    image_tag = f"{ecr_uri}:lazy-embedding-fix-{timestamp}"
    latest_tag = f"{ecr_uri}:latest"
    
    returncode, stdout, stderr = run_command([
        'docker', 'build', 
        '-t', image_tag,
        '-t', latest_tag,
        '-f', 'Dockerfile',
        '.'
    ])
    
    if returncode != 0:
        print(f"Docker build failed: {stderr}")
        return
    
    print(f"   Built image: {image_tag}")
    
    # Step 3: Push to ECR
    print("\nStep 3: Pushing image to ECR...")
    returncode, stdout, stderr = run_command(['docker', 'push', image_tag])
    if returncode != 0:
        print(f"Push failed: {stderr}")
        return
    
    returncode, stdout, stderr = run_command(['docker', 'push', latest_tag])
    if returncode != 0:
        print(f"Push latest failed: {stderr}")
        return
    
    print("   Image pushed successfully")
    
    # Step 4: Get current task definition
    print("\nStep 4: Getting current task definition...")
    ecs = boto3.client('ecs', region_name=AWS_REGION)
    
    # Get the latest task definition
    response = ecs.list_task_definitions(
        familyPrefix=TASK_FAMILY,
        sort='DESC',
        maxResults=1
    )
    
    if not response['taskDefinitionArns']:
        print("No task definitions found!")
        return
    
    current_task_def_arn = response['taskDefinitionArns'][0]
    print(f"   Current task definition: {current_task_def_arn}")
    
    # Describe the task definition
    response = ecs.describe_task_definition(taskDefinition=current_task_def_arn)
    task_def = response['taskDefinition']
    
    # Step 5: Create new task definition with updated image
    print("\nStep 5: Creating new task definition...")
    
    # Update container image
    container_defs = task_def['containerDefinitions']
    for container in container_defs:
        if container['name'] == 'multimodal-librarian':
            container['image'] = image_tag
            print(f"   Updated container image to: {image_tag}")
    
    # Register new task definition
    new_task_def = ecs.register_task_definition(
        family=task_def['family'],
        taskRoleArn=task_def.get('taskRoleArn'),
        executionRoleArn=task_def.get('executionRoleArn'),
        networkMode=task_def.get('networkMode'),
        containerDefinitions=container_defs,
        volumes=task_def.get('volumes', []),
        placementConstraints=task_def.get('placementConstraints', []),
        requiresCompatibilities=task_def.get('requiresCompatibilities', []),
        cpu=task_def.get('cpu'),
        memory=task_def.get('memory'),
        runtimePlatform=task_def.get('runtimePlatform'),
    )
    
    new_revision = new_task_def['taskDefinition']['revision']
    new_task_def_arn = new_task_def['taskDefinition']['taskDefinitionArn']
    print(f"   New task definition: {TASK_FAMILY}:{new_revision}")
    
    # Step 6: Update ECS service
    print("\nStep 6: Updating ECS service...")
    ecs.update_service(
        cluster=ECS_CLUSTER,
        service=ECS_SERVICE,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    print("   Service update initiated")
    
    # Step 7: Monitor deployment
    print("\nStep 7: Monitoring deployment...")
    print("   Waiting for new task to start...")
    
    max_wait = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        response = ecs.describe_services(
            cluster=ECS_CLUSTER,
            services=[ECS_SERVICE]
        )
        
        if response['services']:
            service = response['services'][0]
            running = service.get('runningCount', 0)
            desired = service.get('desiredCount', 1)
            pending = service.get('pendingCount', 0)
            
            # Check deployments
            deployments = service.get('deployments', [])
            primary = next((d for d in deployments if d['status'] == 'PRIMARY'), None)
            
            if primary:
                primary_running = primary.get('runningCount', 0)
                primary_desired = primary.get('desiredCount', 1)
                
                print(f"   Running: {running}/{desired}, Primary deployment: {primary_running}/{primary_desired}")
                
                if primary_running >= primary_desired and len(deployments) == 1:
                    print("\n   ✓ Deployment complete!")
                    break
        
        time.sleep(15)
    else:
        print("\n   ⚠ Deployment still in progress after 5 minutes")
        print("   Monitor with: aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service-alb")
    
    # Save deployment info
    deployment_info = {
        "timestamp": timestamp,
        "image_tag": image_tag,
        "task_definition": f"{TASK_FAMILY}:{new_revision}",
        "fix_description": "Lazy embedding model loading to prevent health check timeouts",
        "changes": [
            "OpenSearch client connect() no longer loads embedding model",
            "Embedding model loads lazily on first generate_embedding() call",
            "Health checks can pass immediately after OpenSearch connection"
        ]
    }
    
    output_file = f"lazy-embedding-fix-deployment-{timestamp}.json"
    with open(output_file, 'w') as f:
        json.dump(deployment_info, f, indent=2)
    
    print(f"\nDeployment info saved to: {output_file}")
    
    print("\n" + "=" * 70)
    print("DEPLOYMENT SUMMARY")
    print("=" * 70)
    print(f"Image: {image_tag}")
    print(f"Task Definition: {TASK_FAMILY}:{new_revision}")
    print()
    print("The fix defers SentenceTransformer loading until first use,")
    print("allowing health checks to pass immediately after startup.")
    print()
    print("Monitor health with:")
    print(f"  curl https://d2ycx9s8ybqn8z.cloudfront.net/health/simple")


if __name__ == '__main__':
    main()
