#!/usr/bin/env python3
"""
Deploy Startup Logging Fix

This script deploys the startup logging fix that adds comprehensive
orchestration-level logging to identify which component is hanging during startup.

The fix adds:
1. Step-by-step logging for every initialization
2. Timeout protection on all async calls
3. Clear success/failure indicators
4. Visual markers for easy log scanning
"""

import boto3
import json
import time
import sys
from datetime import datetime

def deploy_startup_logging_fix():
    """Deploy the startup logging fix to production."""
    
    print("=" * 80)
    print("DEPLOYING STARTUP LOGGING FIX")
    print("=" * 80)
    print()
    
    # Initialize AWS clients
    ecs_client = boto3.client('ecs', region_name='us-east-1')
    ecr_client = boto3.client('ecr', region_name='us-east-1')
    
    cluster_name = 'multimodal-librarian-prod'
    service_name = 'multimodal-librarian-service'
    repository_name = 'multimodal-librarian'
    
    print("Step 1: Building new Docker image with logging fix...")
    print("-" * 80)
    
    # Build timestamp tag
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    image_tag = f"startup-logging-fix-{timestamp}"
    
    print(f"Image tag: {image_tag}")
    
    # Get ECR repository URI
    try:
        response = ecr_client.describe_repositories(repositoryNames=[repository_name])
        repository_uri = response['repositories'][0]['repositoryUri']
        print(f"Repository URI: {repository_uri}")
    except Exception as e:
        print(f"Error getting repository URI: {e}")
        return False
    
    # Build and push Docker image
    import subprocess
    
    print("\nBuilding Docker image...")
    build_cmd = f"docker build -t {repository_name}:{image_tag} ."
    result = subprocess.run(build_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error building image: {result.stderr}")
        return False
    
    print("✓ Docker image built successfully")
    
    # Tag image for ECR
    print("\nTagging image for ECR...")
    tag_cmd = f"docker tag {repository_name}:{image_tag} {repository_uri}:{image_tag}"
    result = subprocess.run(tag_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error tagging image: {result.stderr}")
        return False
    
    print("✓ Image tagged successfully")
    
    # Login to ECR
    print("\nLogging in to ECR...")
    login_cmd = "aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin " + repository_uri.split('/')[0]
    result = subprocess.run(login_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error logging in to ECR: {result.stderr}")
        return False
    
    print("✓ Logged in to ECR successfully")
    
    # Push image to ECR
    print("\nPushing image to ECR...")
    push_cmd = f"docker push {repository_uri}:{image_tag}"
    result = subprocess.run(push_cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error pushing image: {result.stderr}")
        return False
    
    print("✓ Image pushed to ECR successfully")
    
    print("\nStep 2: Updating ECS service with new image...")
    print("-" * 80)
    
    # Get current task definition
    try:
        response = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not response['services']:
            print(f"Error: Service {service_name} not found")
            return False
        
        current_task_def_arn = response['services'][0]['taskDefinition']
        print(f"Current task definition: {current_task_def_arn}")
        
        # Get task definition details
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        
        # Update container image
        for container in task_def['containerDefinitions']:
            if container['name'] == 'multimodal-librarian':
                old_image = container['image']
                container['image'] = f"{repository_uri}:{image_tag}"
                print(f"Updating image:")
                print(f"  Old: {old_image}")
                print(f"  New: {container['image']}")
        
        # Register new task definition
        new_task_def = {
            'family': task_def['family'],
            'taskRoleArn': task_def.get('taskRoleArn'),
            'executionRoleArn': task_def.get('executionRoleArn'),
            'networkMode': task_def.get('networkMode'),
            'containerDefinitions': task_def['containerDefinitions'],
            'volumes': task_def.get('volumes', []),
            'requiresCompatibilities': task_def.get('requiresCompatibilities', []),
            'cpu': task_def.get('cpu'),
            'memory': task_def.get('memory')
        }
        
        print("\nRegistering new task definition...")
        register_response = ecs_client.register_task_definition(**new_task_def)
        new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
        print(f"✓ New task definition registered: {new_task_def_arn}")
        
        # Update service
        print("\nUpdating service...")
        update_response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True
        )
        
        print("✓ Service update initiated")
        
    except Exception as e:
        print(f"Error updating service: {e}")
        return False
    
    print("\nStep 3: Monitoring deployment...")
    print("-" * 80)
    
    print("\nWaiting for deployment to stabilize...")
    print("This may take several minutes...")
    print()
    
    # Monitor deployment
    max_wait_time = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            service = response['services'][0]
            deployments = service['deployments']
            
            print(f"\rDeployments: {len(deployments)} | ", end='')
            
            for deployment in deployments:
                status = deployment['status']
                desired = deployment['desiredCount']
                running = deployment['runningCount']
                print(f"{status}: {running}/{desired} | ", end='')
            
            # Check if deployment is complete
            if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
                deployment = deployments[0]
                if deployment['runningCount'] == deployment['desiredCount']:
                    print("\n\n✓ Deployment completed successfully!")
                    break
            
            time.sleep(10)
            
        except Exception as e:
            print(f"\nError monitoring deployment: {e}")
            break
    else:
        print("\n\n⚠ Deployment monitoring timed out after 10 minutes")
        print("Check AWS Console for deployment status")
    
    print("\nStep 4: Checking CloudWatch logs for startup logging...")
    print("-" * 80)
    
    print("\nTo view the new startup logs, run:")
    print(f"aws logs tail /ecs/multimodal-librarian-prod --follow --region us-east-1")
    print()
    print("Look for these log markers:")
    print("  - STARTUP EVENT BEGINNING")
    print("  - STEP 1: Initializing startup logger...")
    print("  - STEP 2: Initializing user experience logger...")
    print("  - STEP 3: Initializing minimal server...")
    print("  - STEP 4: Initializing progressive loader...")
    print("  - STEP 5: Starting phase progression...")
    print("  - STEP 6: Initializing cache service...")
    print("  - STEP 7: Starting alert evaluation...")
    print("  - STEP 8: Initializing health monitoring...")
    print("  - STEP 9: Initializing startup alerts...")
    print("  - STEP 10: Logging application ready state...")
    print("  - APPLICATION STARTUP COMPLETED SUCCESSFULLY")
    print()
    print("If you see a TIMEOUT message, that tells you which component is hanging!")
    print()
    
    print("=" * 80)
    print("DEPLOYMENT COMPLETE")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    success = deploy_startup_logging_fix()
    sys.exit(0 if success else 1)
