#!/usr/bin/env python3
"""
Fix circular import issue and deploy updated service.

This script builds a new Docker image with the circular import fix
and deploys it to the production ECS service.
"""

import subprocess
import json
import time
import sys
from datetime import datetime

def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n🔄 {description}")
    print(f"Command: {command}")
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"✅ {description} completed successfully")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
            return result.stdout
        else:
            print(f"❌ {description} failed")
            print(f"Error: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} timed out")
        return None
    except Exception as e:
        print(f"💥 {description} failed with exception: {e}")
        return None

def main():
    """Main deployment process."""
    print("🚀 Starting circular import fix deployment")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Step 1: Build new Docker image
    build_command = """
    docker build -t multimodal-librarian:circular-import-fix . \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    --cache-from multimodal-librarian:latest
    """
    
    if not run_command(build_command, "Building Docker image with circular import fix"):
        print("❌ Failed to build Docker image")
        sys.exit(1)
    
    # Step 2: Get ECR login
    ecr_login = run_command(
        "aws ecr get-login-password --region us-east-1",
        "Getting ECR login token"
    )
    
    if not ecr_login:
        print("❌ Failed to get ECR login")
        sys.exit(1)
    
    # Step 3: Login to ECR
    login_command = f"echo '{ecr_login.strip()}' | docker login --username AWS --password-stdin 591222106065.dkr.ecr.us-east-1.amazonaws.com"
    
    if not run_command(login_command, "Logging into ECR"):
        print("❌ Failed to login to ECR")
        sys.exit(1)
    
    # Step 4: Tag image
    tag_command = "docker tag multimodal-librarian:circular-import-fix 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest"
    
    if not run_command(tag_command, "Tagging Docker image"):
        print("❌ Failed to tag image")
        sys.exit(1)
    
    # Step 5: Push image
    push_command = "docker push 591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest"
    
    if not run_command(push_command, "Pushing Docker image to ECR"):
        print("❌ Failed to push image")
        sys.exit(1)
    
    # Step 6: Force new deployment
    deploy_command = "aws ecs update-service --cluster multimodal-lib-prod-cluster --service multimodal-lib-prod-service --force-new-deployment"
    
    if not run_command(deploy_command, "Forcing new ECS deployment"):
        print("❌ Failed to trigger deployment")
        sys.exit(1)
    
    # Step 7: Wait for deployment to complete
    print("\n⏳ Waiting for deployment to complete...")
    
    for i in range(30):  # Wait up to 15 minutes
        time.sleep(30)
        
        # Check service status
        status_output = run_command(
            "aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service --query 'services[0].deployments[0].{status:status,runningCount:runningCount,pendingCount:pendingCount,desiredCount:desiredCount}' --output json",
            f"Checking deployment status (attempt {i+1}/30)"
        )
        
        if status_output:
            try:
                status = json.loads(status_output)
                print(f"Status: {status['status']}, Running: {status['runningCount']}, Pending: {status['pendingCount']}, Desired: {status['desiredCount']}")
                
                if status['status'] == 'PRIMARY' and status['runningCount'] == status['desiredCount'] and status['pendingCount'] == 0:
                    print("✅ Deployment completed successfully!")
                    break
            except json.JSONDecodeError:
                print("⚠️ Could not parse status response")
        
        if i == 29:
            print("⏰ Deployment timeout - check AWS console for status")
            break
    
    # Step 8: Check task health
    print("\n🏥 Checking task health...")
    
    health_output = run_command(
        "aws ecs describe-tasks --cluster multimodal-lib-prod-cluster --tasks $(aws ecs list-tasks --cluster multimodal-lib-prod-cluster --service-name multimodal-lib-prod-service --query 'taskArns[0]' --output text) --query 'tasks[0].{lastStatus:lastStatus,healthStatus:healthStatus,desiredStatus:desiredStatus}' --output json",
        "Checking task health status"
    )
    
    if health_output:
        try:
            health = json.loads(health_output)
            print(f"Task Status: {health['lastStatus']}, Health: {health['healthStatus']}, Desired: {health['desiredStatus']}")
            
            if health['healthStatus'] == 'HEALTHY':
                print("✅ Service is healthy!")
            else:
                print("⚠️ Service may still be starting up or has health issues")
        except json.JSONDecodeError:
            print("⚠️ Could not parse health response")
    
    # Step 9: Test the fix
    print("\n🧪 Testing the circular import fix...")
    
    # Get recent logs to check for circular import errors
    log_output = run_command(
        "aws logs describe-log-streams --log-group-name /ecs/multimodal-lib-prod-app --order-by LastEventTime --descending --limit 1 --query 'logStreams[0].logStreamName' --output text",
        "Getting latest log stream"
    )
    
    if log_output and log_output.strip() != "None":
        log_stream = log_output.strip()
        
        logs = run_command(
            f"aws logs get-log-events --log-group-name /ecs/multimodal-lib-prod-app --log-stream-name {log_stream} --limit 20 --query 'events[*].message' --output text",
            "Checking recent application logs"
        )
        
        if logs:
            if "circular import" in logs.lower():
                print("❌ Circular import error still present in logs")
            elif "Failed to import Knowledge Graph router" in logs:
                print("❌ Knowledge Graph import error still present")
            elif "Starting minimal FastAPI application" in logs:
                print("✅ Application appears to be starting successfully")
            else:
                print("ℹ️ No obvious errors in recent logs")
    
    print(f"\n🎉 Deployment process completed at {datetime.now().isoformat()}")
    print("Check the AWS ECS console for detailed deployment status")

if __name__ == "__main__":
    main()