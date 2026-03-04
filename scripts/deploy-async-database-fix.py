#!/usr/bin/env python3
"""
Deploy Async Database Initialization Fix

This script rebuilds the Docker image with the async database initialization fix
and deploys it to ECS.

The fix ensures that:
1. Health check endpoint (/health/simple) responds immediately without waiting for databases
2. Database initialization happens asynchronously in the background
3. Application passes ALB health checks during startup
4. Databases are restored (OpenSearch and Neptune) without blocking

Usage:
    python scripts/deploy-async-database-fix.py
"""

import boto3
import subprocess
import time
import sys
from datetime import datetime

# AWS clients
ecr_client = boto3.client('ecr', region_name='us-east-1')
ecs_client = boto3.client('ecs', region_name='us-east-1')

# Configuration
ECR_REPOSITORY = 'multimodal-librarian'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
REGION = 'us-east-1'


def get_ecr_login():
    """Get ECR login credentials."""
    print("🔐 Getting ECR login credentials...")
    
    response = ecr_client.get_authorization_token()
    token = response['authorizationData'][0]['authorizationToken']
    endpoint = response['authorizationData'][0]['proxyEndpoint']
    
    # Extract registry URL
    registry = endpoint.replace('https://', '')
    
    return registry, token


def build_docker_image():
    """Build the Docker image with the async database fix."""
    print("\n🏗️  Building Docker image...")
    print("=" * 80)
    
    # Build command
    cmd = [
        'docker', 'build',
        '-t', f'{ECR_REPOSITORY}:async-db-fix',
        '-t', f'{ECR_REPOSITORY}:latest',
        '-f', 'Dockerfile',
        '.'
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode != 0:
        print(f"❌ Docker build failed with exit code {result.returncode}")
        sys.exit(1)
    
    print("✅ Docker image built successfully")


def push_to_ecr(registry):
    """Push the Docker image to ECR."""
    print("\n📤 Pushing image to ECR...")
    print("=" * 80)
    
    # Get account ID
    sts_client = boto3.client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    
    # Full image name
    image_uri = f"{account_id}.dkr.ecr.{REGION}.amazonaws.com/{ECR_REPOSITORY}"
    
    # Tag image
    print(f"Tagging image as {image_uri}:async-db-fix")
    subprocess.run([
        'docker', 'tag',
        f'{ECR_REPOSITORY}:async-db-fix',
        f'{image_uri}:async-db-fix'
    ], check=True)
    
    subprocess.run([
        'docker', 'tag',
        f'{ECR_REPOSITORY}:latest',
        f'{image_uri}:latest'
    ], check=True)
    
    # Login to ECR
    print("Logging in to ECR...")
    subprocess.run([
        'aws', 'ecr', 'get-login-password',
        '--region', REGION
    ], capture_output=True, check=True, text=True)
    
    login_cmd = f"aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{REGION}.amazonaws.com"
    subprocess.run(login_cmd, shell=True, check=True)
    
    # Push images
    print(f"Pushing {image_uri}:async-db-fix...")
    subprocess.run([
        'docker', 'push',
        f'{image_uri}:async-db-fix'
    ], check=True)
    
    print(f"Pushing {image_uri}:latest...")
    subprocess.run([
        'docker', 'push',
        f'{image_uri}:latest'
    ], check=True)
    
    print(f"✅ Images pushed to ECR: {image_uri}")
    return f"{image_uri}:async-db-fix"


def force_new_deployment():
    """Force a new deployment of the ECS service."""
    print("\n🚀 Forcing new deployment...")
    print("=" * 80)
    
    response = ecs_client.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        forceNewDeployment=True
    )
    
    print(f"✅ Deployment initiated")
    return response


def monitor_deployment():
    """Monitor the deployment progress."""
    print("\n📊 Monitoring deployment...")
    print("=" * 80)
    
    max_wait_time = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = response['services'][0]
        deployments = service['deployments']
        
        print(f"\n⏰ Time elapsed: {int(time.time() - start_time)}s")
        print(f"📦 Deployments: {len(deployments)}")
        
        for deployment in deployments:
            status = deployment['status']
            desired = deployment['desiredCount']
            running = deployment['runningCount']
            pending = deployment['pendingCount']
            
            print(f"   Status: {status}")
            print(f"   Desired: {desired}, Running: {running}, Pending: {pending}")
        
        # Check if deployment is complete
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            deployment = deployments[0]
            if deployment['runningCount'] == deployment['desiredCount']:
                print("\n✅ Deployment completed successfully!")
                return True
        
        # Check for stopped tasks
        tasks_response = ecs_client.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='STOPPED'
        )
        
        if tasks_response['taskArns']:
            print(f"\n⚠️  Found {len(tasks_response['taskArns'])} stopped tasks")
            # Get details of the most recent stopped task
            if tasks_response['taskArns']:
                task_details = ecs_client.describe_tasks(
                    cluster=CLUSTER_NAME,
                    tasks=[tasks_response['taskArns'][0]]
                )
                if task_details['tasks']:
                    task = task_details['tasks'][0]
                    print(f"   Stop reason: {task.get('stoppedReason', 'Unknown')}")
        
        time.sleep(15)
    
    print("\n⏰ Deployment monitoring timed out after 10 minutes")
    return False


def verify_fix():
    """Verify the async database fix is working."""
    print("\n🔍 Verifying async database fix...")
    
    # Get the ALB DNS name
    response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = response['services'][0]
    load_balancers = service.get('loadBalancers', [])
    
    if not load_balancers:
        print("⚠️  No load balancer found for service")
        return
    
    target_group_arn = load_balancers[0]['targetGroupArn']
    
    # Get ALB from target group
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    tg_response = elbv2_client.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    lb_arns = tg_response['TargetGroups'][0]['LoadBalancerArns']
    if lb_arns:
        lb_response = elbv2_client.describe_load_balancers(
            LoadBalancerArns=[lb_arns[0]]
        )
        dns_name = lb_response['LoadBalancers'][0]['DNSName']
        
        print(f"\n📍 Service URL: http://{dns_name}")
        print(f"   Health Check: http://{dns_name}/health/simple")
        print(f"   Database Status: http://{dns_name}/api/health/databases")
        print("\n💡 Verification commands:")
        print(f"   # Check health (should respond immediately)")
        print(f"   curl http://{dns_name}/health/simple")
        print(f"   ")
        print(f"   # Check database initialization status")
        print(f"   curl http://{dns_name}/api/health/databases")


def main():
    """Main execution function."""
    print("=" * 80)
    print("DEPLOY ASYNC DATABASE INITIALIZATION FIX")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Repository: {ECR_REPOSITORY}")
    print(f"Cluster: {CLUSTER_NAME}")
    print(f"Service: {SERVICE_NAME}")
    print()
    print("This script will:")
    print("1. Build Docker image with async database initialization fix")
    print("2. Push image to ECR")
    print("3. Force new deployment")
    print("4. Monitor deployment progress")
    print("5. Verify the fix is working")
    print("=" * 80)
    
    try:
        # Get ECR credentials
        registry, token = get_ecr_login()
        
        # Build Docker image
        build_docker_image()
        
        # Push to ECR
        image_uri = push_to_ecr(registry)
        
        # Force new deployment
        force_new_deployment()
        
        # Monitor deployment
        success = monitor_deployment()
        
        if success:
            # Verify fix
            verify_fix()
            
            print("\n" + "=" * 80)
            print("✅ ASYNC DATABASE FIX DEPLOYED SUCCESSFULLY")
            print("=" * 80)
            print("\nThe fix includes:")
            print("✓ Health check endpoint responds immediately")
            print("✓ Database initialization happens asynchronously")
            print("✓ No blocking on OpenSearch or Neptune connections")
            print("✓ Configurable timeouts (10s default)")
            print("\nNext steps:")
            print("1. Verify health check responds quickly: curl <ALB>/health/simple")
            print("2. Check database status: curl <ALB>/api/health/databases")
            print("3. Run: python scripts/restore-databases-with-async-init.py")
        else:
            print("\n" + "=" * 80)
            print("⚠️  DEPLOYMENT DID NOT COMPLETE WITHIN TIMEOUT")
            print("=" * 80)
            print("\nCheck:")
            print("1. ECS console for task status")
            print("2. CloudWatch logs for errors")
            print("3. ALB target health")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
