#!/usr/bin/env python3
"""
Deploy Minimal Health Check Fix

This script deploys the minimal health check endpoint that bypasses all middleware
to fix ALB health check timeouts.

Root Cause:
- The /health/simple endpoint was going through middleware (session, request tracking, etc.)
- Middleware was adding latency and causing ALB timeouts
- Session middleware errors were causing additional delays

Solution:
- Register /health/simple endpoint BEFORE any middleware is added
- Endpoint returns immediately without any dependencies
- No database checks, no model checks, no blocking operations
"""

import boto3
import json
import time
import sys
from datetime import datetime

def log(message):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def rebuild_and_push_image():
    """Rebuild Docker image and push to ECR."""
    log("=" * 80)
    log("STEP 1: Rebuilding Docker image with minimal health check fix")
    log("=" * 80)
    
    import subprocess
    
    # Build image
    log("Building Docker image...")
    result = subprocess.run(
        ["docker", "build", "-t", "multimodal-librarian:latest", "."],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        log(f"ERROR: Docker build failed: {result.stderr}")
        return False
    
    log("✓ Docker image built successfully")
    
    # Get ECR login
    log("Logging into ECR...")
    ecr_client = boto3.client('ecr', region_name='us-east-1')
    
    try:
        import base64
        auth_token = ecr_client.get_authorization_token()
        token = auth_token['authorizationData'][0]['authorizationToken']
        decoded_token = base64.b64decode(token).decode('utf-8')
        username, password = decoded_token.split(':')
        registry = auth_token['authorizationData'][0]['proxyEndpoint']
        
        # Docker login
        result = subprocess.run(
            ["docker", "login", "-u", username, "-p", password, registry],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            log(f"ERROR: Docker login failed: {result.stderr}")
            return False
        
        log("✓ Logged into ECR successfully")
        
    except Exception as e:
        log(f"ERROR: Failed to get ECR credentials: {e}")
        return False
    
    # Tag and push image
    ecr_repo = "591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-lib-prod-app"
    image_tag = f"{ecr_repo}:latest"
    
    log(f"Tagging image as {image_tag}...")
    result = subprocess.run(
        ["docker", "tag", "multimodal-librarian:latest", image_tag],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        log(f"ERROR: Docker tag failed: {result.stderr}")
        return False
    
    log("Pushing image to ECR...")
    result = subprocess.run(
        ["docker", "push", image_tag],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        log(f"ERROR: Docker push failed: {result.stderr}")
        return False
    
    log("✓ Image pushed to ECR successfully")
    return True

def force_new_deployment():
    """Force ECS to deploy new task definition."""
    log("=" * 80)
    log("STEP 2: Forcing new ECS deployment")
    log("=" * 80)
    
    ecs_client = boto3.client('ecs', region_name='us-east-1')
    
    cluster_name = "multimodal-librarian-prod-cluster"
    service_name = "multimodal-librarian-prod-service"
    
    try:
        log(f"Forcing new deployment for service {service_name}...")
        response = ecs_client.update_service(
            cluster=cluster_name,
            service=service_name,
            forceNewDeployment=True
        )
        
        log("✓ New deployment initiated successfully")
        log(f"Deployment ID: {response['service']['deployments'][0]['id']}")
        
        return True
        
    except Exception as e:
        log(f"ERROR: Failed to force new deployment: {e}")
        return False

def wait_for_deployment(timeout_minutes=10):
    """Wait for deployment to complete."""
    log("=" * 80)
    log("STEP 3: Waiting for deployment to complete")
    log("=" * 80)
    
    ecs_client = boto3.client('ecs', region_name='us-east-1')
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    
    cluster_name = "multimodal-librarian-prod-cluster"
    service_name = "multimodal-librarian-prod-service"
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34"
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Check service status
            response = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            service = response['services'][0]
            deployments = service['deployments']
            
            log(f"Active deployments: {len(deployments)}")
            for deployment in deployments:
                log(f"  - Status: {deployment['status']}, "
                    f"Running: {deployment['runningCount']}, "
                    f"Desired: {deployment['desiredCount']}")
            
            # Check if deployment is stable (only one deployment with desired count)
            if len(deployments) == 1 and deployments[0]['runningCount'] == deployments[0]['desiredCount']:
                log("✓ Deployment is stable")
                
                # Check target health
                log("Checking target health...")
                health_response = elbv2_client.describe_target_health(
                    TargetGroupArn=target_group_arn
                )
                
                healthy_targets = [t for t in health_response['TargetHealthDescriptions'] 
                                 if t['TargetHealth']['State'] == 'healthy']
                
                log(f"Healthy targets: {len(healthy_targets)}/{len(health_response['TargetHealthDescriptions'])}")
                
                if len(healthy_targets) > 0:
                    log("=" * 80)
                    log("✓ DEPLOYMENT SUCCESSFUL - Targets are healthy!")
                    log("=" * 80)
                    return True
                else:
                    log("Waiting for targets to become healthy...")
            
        except Exception as e:
            log(f"ERROR checking deployment status: {e}")
        
        time.sleep(30)
    
    log("=" * 80)
    log("✗ DEPLOYMENT TIMEOUT - Deployment did not complete within timeout")
    log("=" * 80)
    return False

def verify_health_check():
    """Verify the health check endpoint is working."""
    log("=" * 80)
    log("STEP 4: Verifying health check endpoint")
    log("=" * 80)
    
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    
    # Get ALB DNS name
    load_balancer_arn = "arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb-v2/e8c0f3a8c5e5e5e5"
    
    try:
        response = elbv2_client.describe_load_balancers(
            LoadBalancerArns=[load_balancer_arn]
        )
        
        dns_name = response['LoadBalancers'][0]['DNSName']
        health_url = f"http://{dns_name}/health/simple"
        
        log(f"Testing health check endpoint: {health_url}")
        
        import requests
        
        # Test health check multiple times
        success_count = 0
        for i in range(5):
            try:
                start = time.time()
                response = requests.get(health_url, timeout=5)
                duration = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    success_count += 1
                    log(f"  Test {i+1}: ✓ 200 OK ({duration:.0f}ms)")
                else:
                    log(f"  Test {i+1}: ✗ {response.status_code} ({duration:.0f}ms)")
                
                time.sleep(2)
                
            except Exception as e:
                log(f"  Test {i+1}: ✗ ERROR: {e}")
        
        if success_count >= 4:
            log("=" * 80)
            log("✓ HEALTH CHECK VERIFICATION SUCCESSFUL")
            log("=" * 80)
            return True
        else:
            log("=" * 80)
            log(f"✗ HEALTH CHECK VERIFICATION FAILED ({success_count}/5 successful)")
            log("=" * 80)
            return False
            
    except Exception as e:
        log(f"ERROR: Failed to verify health check: {e}")
        return False

def main():
    """Main deployment function."""
    log("=" * 80)
    log("DEPLOYING MINIMAL HEALTH CHECK FIX")
    log("=" * 80)
    log("")
    log("This deployment fixes ALB health check timeouts by:")
    log("1. Registering /health/simple endpoint BEFORE middleware")
    log("2. Ensuring endpoint returns immediately without dependencies")
    log("3. Bypassing all middleware (session, request tracking, etc.)")
    log("")
    
    # Step 1: Rebuild and push image
    if not rebuild_and_push_image():
        log("✗ DEPLOYMENT FAILED: Could not rebuild/push image")
        sys.exit(1)
    
    # Step 2: Force new deployment
    if not force_new_deployment():
        log("✗ DEPLOYMENT FAILED: Could not force new deployment")
        sys.exit(1)
    
    # Step 3: Wait for deployment
    if not wait_for_deployment():
        log("✗ DEPLOYMENT FAILED: Deployment did not complete successfully")
        sys.exit(1)
    
    # Step 4: Verify health check
    if not verify_health_check():
        log("⚠ WARNING: Health check verification failed, but deployment completed")
        log("Please check ALB target health manually")
    
    log("=" * 80)
    log("✓ DEPLOYMENT COMPLETED SUCCESSFULLY")
    log("=" * 80)
    log("")
    log("Next steps:")
    log("1. Monitor ALB target health in AWS Console")
    log("2. Check application logs for any errors")
    log("3. Test the application endpoint")
    log("")

if __name__ == "__main__":
    main()
