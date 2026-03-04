#!/usr/bin/env python3
"""
Deploy with Startup Optimization
This script deploys the application with optimized health check configuration
for multi-phase startup with progressive model loading.
"""

import boto3
import json
import subprocess
import time
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
TASK_FAMILY = "multimodal-lib-prod-app"
AWS_REGION = "us-east-1"
ECR_REPOSITORY = "multimodal-librarian"

# Health check configuration for startup optimization
HEALTH_CHECK_PATH = "/health/minimal"  # Correct path (no /api prefix) - matches minimal_server.py
HEALTH_CHECK_INTERVAL = 30
HEALTH_CHECK_TIMEOUT = 15
HEALTH_CHECK_RETRIES = 5
HEALTH_CHECK_START_PERIOD = 300  # 5 minutes for AI model loading

# Color codes for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_status(message: str):
    """Print success status message."""
    print(f"{Colors.GREEN}✓{Colors.NC} {message}")

def print_error(message: str):
    """Print error message."""
    print(f"{Colors.RED}✗{Colors.NC} {message}")

def print_info(message: str):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ{Colors.NC} {message}")

def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.NC} {message}")

def print_header(message: str):
    """Print header message."""
    print(f"\n{Colors.BLUE}{'=' * 60}{Colors.NC}")
    print(f"{Colors.BLUE}{message}{Colors.NC}")
    print(f"{Colors.BLUE}{'=' * 60}{Colors.NC}\n")

def check_prerequisites():
    """Check if required tools are installed."""
    print_info("Checking prerequisites...")
    
    # Check AWS CLI
    try:
        subprocess.run(["aws", "--version"], capture_output=True, check=True)
        print_status("AWS CLI is installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("AWS CLI is not installed. Please install it first.")
        sys.exit(1)
    
    # Check Docker
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        print_status("Docker is installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Docker is not installed. Please install it first.")
        sys.exit(1)

def get_ecr_repository_uri() -> str:
    """Get ECR repository URI."""
    print_info("Getting ECR repository URI...")
    
    try:
        ecr = boto3.client('ecr', region_name=AWS_REGION)
        response = ecr.describe_repositories(repositoryNames=[ECR_REPOSITORY])
        
        if response['repositories']:
            repo_uri = response['repositories'][0]['repositoryUri']
            print_status(f"ECR repository found: {repo_uri}")
            return repo_uri
        else:
            print_error(f"ECR repository '{ECR_REPOSITORY}' not found")
            sys.exit(1)
    except Exception as e:
        print_error(f"Failed to get ECR repository: {e}")
        sys.exit(1)

def build_and_push_image(repo_uri: str):
    """Build and push Docker image to ECR."""
    print_info("Building Docker image...")
    
    try:
        # Get ECR login token
        ecr = boto3.client('ecr', region_name=AWS_REGION)
        auth_response = ecr.get_authorization_token()
        
        # Extract credentials
        import base64
        token = auth_response['authorizationData'][0]['authorizationToken']
        endpoint = auth_response['authorizationData'][0]['proxyEndpoint']
        decoded_token = base64.b64decode(token).decode('utf-8')
        username, password = decoded_token.split(':')
        
        # Docker login
        login_cmd = f"echo {password} | docker login --username {username} --password-stdin {endpoint}"
        subprocess.run(login_cmd, shell=True, check=True, capture_output=True)
        print_status("Logged into ECR")
        
        # Build image
        print_info("Building Docker image (this may take several minutes)...")
        subprocess.run(
            ["docker", "build", "-t", f"{repo_uri}:latest", "."],
            check=True,
            capture_output=True
        )
        print_status("Docker image built successfully")
        
        # Tag with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        subprocess.run(
            ["docker", "tag", f"{repo_uri}:latest", f"{repo_uri}:{timestamp}"],
            check=True,
            capture_output=True
        )
        print_status(f"Image tagged with timestamp: {timestamp}")
        
        # Push images
        print_info("Pushing Docker images to ECR...")
        subprocess.run(
            ["docker", "push", f"{repo_uri}:latest"],
            check=True,
            capture_output=True
        )
        print_status("Pushed latest image")
        
        try:
            subprocess.run(
                ["docker", "push", f"{repo_uri}:{timestamp}"],
                check=True,
                capture_output=True,
                timeout=1800
            )
            print_status("Pushed timestamped image")
        except Exception:
            print_warning("Failed to push timestamped image (non-critical)")
            
    except Exception as e:
        print_error(f"Failed to build and push image: {e}")
        sys.exit(1)

def update_task_definition(repo_uri: str) -> str:
    """Update task definition with optimized health checks."""
    print_info("Updating task definition with optimized health checks...")
    
    try:
        ecs = boto3.client('ecs', region_name=AWS_REGION)
        
        # Get current task definition
        response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
        current_task_def = response['taskDefinition']
        
        # Create new task definition with updated health check
        container_def = current_task_def['containerDefinitions'][0].copy()
        container_def['image'] = f"{repo_uri}:latest"
        container_def['healthCheck'] = {
            'command': [
                'CMD-SHELL',
                f'curl -f http://localhost:8000{HEALTH_CHECK_PATH} || exit 1'
            ],
            'interval': HEALTH_CHECK_INTERVAL,
            'timeout': HEALTH_CHECK_TIMEOUT,
            'retries': HEALTH_CHECK_RETRIES,
            'startPeriod': HEALTH_CHECK_START_PERIOD
        }
        
        # Register new task definition
        new_task_def = {
            'family': current_task_def['family'],
            'taskRoleArn': current_task_def.get('taskRoleArn'),
            'executionRoleArn': current_task_def.get('executionRoleArn'),
            'networkMode': current_task_def['networkMode'],
            'requiresCompatibilities': current_task_def['requiresCompatibilities'],
            'cpu': current_task_def['cpu'],
            'memory': current_task_def['memory'],
            'containerDefinitions': [container_def],
            # Explicitly set ephemeral storage to 50GB for model caching
            'ephemeralStorage': {
                'sizeInGiB': 50
            }
        }
        
        register_response = ecs.register_task_definition(**new_task_def)
        task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
        
        print_status(f"New task definition registered: {task_def_arn}")
        return task_def_arn
        
    except Exception as e:
        print_error(f"Failed to update task definition: {e}")
        sys.exit(1)

def update_alb_health_check():
    """Update ALB target group health check."""
    print_info("Updating ALB target group health check...")
    
    try:
        elbv2 = boto3.client('elbv2', region_name=AWS_REGION)
        
        # Find target group
        response = elbv2.describe_target_groups()
        target_group_arn = None
        
        for tg in response['TargetGroups']:
            if 'multimodal-lib-prod' in tg['TargetGroupName']:
                target_group_arn = tg['TargetGroupArn']
                break
        
        if not target_group_arn:
            print_warning("Target group not found, skipping ALB health check update")
            return
        
        # Update target group health check
        elbv2.modify_target_group(
            TargetGroupArn=target_group_arn,
            HealthCheckPath=HEALTH_CHECK_PATH,
            HealthCheckIntervalSeconds=HEALTH_CHECK_INTERVAL,
            HealthCheckTimeoutSeconds=HEALTH_CHECK_TIMEOUT,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=5
        )
        
        print_status("ALB target group health check updated")
        
    except Exception as e:
        print_warning(f"Failed to update ALB health check (non-critical): {e}")

def update_ecs_service(task_def_arn: str):
    """Update ECS service with new task definition."""
    print_info("Updating ECS service...")
    
    try:
        ecs = boto3.client('ecs', region_name=AWS_REGION)
        
        ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            taskDefinition=task_def_arn,
            forceNewDeployment=True
        )
        
        print_status("ECS service update initiated")
        
    except Exception as e:
        print_error(f"Failed to update ECS service: {e}")
        sys.exit(1)

def wait_for_deployment() -> bool:
    """Wait for deployment to complete."""
    print_info("Waiting for deployment to complete...")
    print_info("This may take 5-10 minutes due to startup optimization...")
    
    try:
        ecs = boto3.client('ecs', region_name=AWS_REGION)
        
        # Wait for service to stabilize
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 40  # 10 minutes max
            }
        )
        
        print_status("Deployment completed successfully")
        return True
        
    except Exception as e:
        print_warning(f"Service stabilization wait timed out: {e}")
        print_info("Checking service status manually...")
        
        try:
            ecs = boto3.client('ecs', region_name=AWS_REGION)
            response = ecs.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            if response['services']:
                service = response['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print_info(f"Service Status:")
                print(f"  Running tasks: {running_count}")
                print(f"  Desired tasks: {desired_count}")
                
                if running_count == desired_count:
                    print_status("Deployment completed successfully")
                    return True
                else:
                    print_warning(f"Service not fully healthy yet ({running_count}/{desired_count} tasks)")
                    print_info("Tasks may still be starting up. Check CloudWatch logs for details.")
                    return False
        except Exception as e2:
            print_error(f"Failed to check service status: {e2}")
            return False

def verify_health_endpoints():
    """Verify health endpoints are responding."""
    print_info("Verifying health endpoints...")
    
    try:
        elbv2 = boto3.client('elbv2', region_name=AWS_REGION)
        
        # Find ALB
        response = elbv2.describe_load_balancers()
        alb_dns = None
        
        for lb in response['LoadBalancers']:
            if 'multimodal-lib-prod' in lb['LoadBalancerName']:
                alb_dns = lb['DNSName']
                break
        
        if not alb_dns:
            print_warning("Could not find ALB DNS name")
            return
        
        print_info(f"Testing health endpoints via ALB: {alb_dns}")
        
        import requests
        
        # Test minimal health endpoint
        try:
            response = requests.get(f"http://{alb_dns}{HEALTH_CHECK_PATH}", timeout=10)
            if response.status_code == 200:
                print_status("Minimal health endpoint responding")
            else:
                print_warning(f"Minimal health endpoint returned status {response.status_code}")
        except Exception:
            print_warning("Minimal health endpoint not responding yet")
        
        # Test ready endpoint
        try:
            response = requests.get(f"http://{alb_dns}/api/health/ready", timeout=10)
            if response.status_code == 200:
                print_status("Ready health endpoint responding")
            else:
                print_info("Ready endpoint not responding (models may still be loading)")
        except Exception:
            print_info("Ready endpoint not responding (models may still be loading)")
        
        # Test full endpoint
        try:
            response = requests.get(f"http://{alb_dns}/api/health/full", timeout=10)
            if response.status_code == 200:
                print_status("Full health endpoint responding")
            else:
                print_info("Full endpoint not responding (all models may not be loaded yet)")
        except Exception:
            print_info("Full endpoint not responding (all models may not be loaded yet)")
            
    except Exception as e:
        print_warning(f"Failed to verify health endpoints: {e}")

def main():
    """Main deployment function."""
    print_header("Deployment with Startup Optimization")
    
    print(f"{Colors.YELLOW}Configuration:{Colors.NC}")
    print(f"  Cluster: {CLUSTER_NAME}")
    print(f"  Service: {SERVICE_NAME}")
    print(f"  Task Family: {TASK_FAMILY}")
    print(f"  Region: {AWS_REGION}")
    print(f"  Health Check Path: {HEALTH_CHECK_PATH}")
    print(f"  Health Check Start Period: {HEALTH_CHECK_START_PERIOD}s")
    print()
    
    # Pre-flight checks
    check_prerequisites()
    print()
    
    # Get ECR repository
    repo_uri = get_ecr_repository_uri()
    print()
    
    # Build and push image
    build_and_push_image(repo_uri)
    print()
    
    # Update task definition
    task_def_arn = update_task_definition(repo_uri)
    print()
    
    # Update ALB health check
    update_alb_health_check()
    print()
    
    # Update ECS service
    update_ecs_service(task_def_arn)
    print()
    
    # Wait for deployment
    deployment_success = wait_for_deployment()
    print()
    
    # Verify health endpoints
    verify_health_endpoints()
    print()
    
    print_header("Deployment Complete!")
    
    print(f"{Colors.YELLOW}Next Steps:{Colors.NC}")
    print("1. Monitor CloudWatch logs for startup progress")
    print("2. Check health endpoints:")
    print("   - /api/health/minimal (basic server ready)")
    print("   - /api/health/ready (essential models loaded)")
    print("   - /api/health/full (all models loaded)")
    print("3. Monitor startup metrics in CloudWatch")
    print()
    
    print(f"{Colors.BLUE}Startup Timeline:{Colors.NC}")
    print("  0-30s:   Minimal startup (basic API ready)")
    print("  30s-2m:  Essential models loading")
    print("  2m-5m:   Full capability loading")
    print()
    
    return 0 if deployment_success else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_error("\nDeployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)
