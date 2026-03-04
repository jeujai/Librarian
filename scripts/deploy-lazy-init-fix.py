#!/usr/bin/env python3
"""
Deploy Lazy Initialization Fix

This script deploys the fix for module-level database initialization that was
blocking application startup and causing health check failures.

The fix converts synchronous module-level VectorStore initialization to lazy
initialization that only connects when components are actually used.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

def log(message: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def run_command(command: list, description: str) -> dict:
    """Run a command and return the result."""
    log(f"Running: {description}")
    log(f"Command: {' '.join(command)}")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        log(f"✓ {description} completed successfully")
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.CalledProcessError as e:
        log(f"✗ {description} failed: {e}", "ERROR")
        log(f"STDOUT: {e.stdout}", "ERROR")
        log(f"STDERR: {e.stderr}", "ERROR")
        return {
            "success": False,
            "stdout": e.stdout,
            "stderr": e.stderr,
            "error": str(e)
        }

def main():
    """Main deployment function."""
    log("=" * 80)
    log("LAZY INITIALIZATION FIX DEPLOYMENT")
    log("=" * 80)
    
    deployment_results = {
        "start_time": datetime.now().isoformat(),
        "steps": []
    }
    
    # Step 1: Verify we're in the right directory
    log("STEP 1: Verifying project structure")
    if not Path("src/multimodal_librarian/api/routers/chat.py").exists():
        log("ERROR: Not in project root directory", "ERROR")
        sys.exit(1)
    log("✓ Project structure verified")
    
    # Step 2: Build new Docker image
    log("STEP 2: Building Docker image with lazy initialization fix")
    build_result = run_command(
        ["docker", "build", "-t", "multimodal-lib-prod-app:lazy-init-fix", "."],
        "Docker image build"
    )
    deployment_results["steps"].append({
        "step": "build_image",
        "success": build_result["success"]
    })
    
    if not build_result["success"]:
        log("Failed to build Docker image", "ERROR")
        sys.exit(1)
    
    # Step 3: Tag image for ECR
    log("STEP 3: Tagging image for ECR")
    tag_result = run_command(
        [
            "docker", "tag",
            "multimodal-lib-prod-app:lazy-init-fix",
            "591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-lib-prod-app:lazy-init-fix"
        ],
        "Docker image tagging"
    )
    deployment_results["steps"].append({
        "step": "tag_image",
        "success": tag_result["success"]
    })
    
    if not tag_result["success"]:
        log("Failed to tag Docker image", "ERROR")
        sys.exit(1)
    
    # Step 4: Login to ECR
    log("STEP 4: Logging in to ECR")
    login_result = run_command(
        [
            "aws", "ecr", "get-login-password",
            "--region", "us-east-1"
        ],
        "ECR login password retrieval"
    )
    
    if login_result["success"]:
        login_password = login_result["stdout"].strip()
        docker_login_result = subprocess.run(
            [
                "docker", "login",
                "--username", "AWS",
                "--password-stdin",
                "591222106065.dkr.ecr.us-east-1.amazonaws.com"
            ],
            input=login_password,
            capture_output=True,
            text=True
        )
        
        if docker_login_result.returncode == 0:
            log("✓ ECR login successful")
            deployment_results["steps"].append({
                "step": "ecr_login",
                "success": True
            })
        else:
            log("Failed to login to ECR", "ERROR")
            deployment_results["steps"].append({
                "step": "ecr_login",
                "success": False
            })
            sys.exit(1)
    else:
        log("Failed to get ECR login password", "ERROR")
        sys.exit(1)
    
    # Step 5: Push image to ECR
    log("STEP 5: Pushing image to ECR")
    push_result = run_command(
        [
            "docker", "push",
            "591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-lib-prod-app:lazy-init-fix"
        ],
        "Docker image push to ECR"
    )
    deployment_results["steps"].append({
        "step": "push_image",
        "success": push_result["success"]
    })
    
    if not push_result["success"]:
        log("Failed to push Docker image to ECR", "ERROR")
        sys.exit(1)
    
    # Step 6: Update ECS task definition
    log("STEP 6: Updating ECS task definition")
    
    # Get current task definition
    get_task_def_result = run_command(
        [
            "aws", "ecs", "describe-task-definition",
            "--task-definition", "multimodal-lib-prod-app",
            "--region", "us-east-1"
        ],
        "Get current task definition"
    )
    
    if not get_task_def_result["success"]:
        log("Failed to get current task definition", "ERROR")
        sys.exit(1)
    
    task_def = json.loads(get_task_def_result["stdout"])
    
    # Update image in task definition
    container_definitions = task_def["taskDefinition"]["containerDefinitions"]
    for container in container_definitions:
        if container["name"] == "multimodal-lib-prod-app":
            container["image"] = "591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-lib-prod-app:lazy-init-fix"
            log(f"Updated container image to: {container['image']}")
    
    # Create new task definition revision
    new_task_def = {
        "family": task_def["taskDefinition"]["family"],
        "taskRoleArn": task_def["taskDefinition"]["taskRoleArn"],
        "executionRoleArn": task_def["taskDefinition"]["executionRoleArn"],
        "networkMode": task_def["taskDefinition"]["networkMode"],
        "containerDefinitions": container_definitions,
        "requiresCompatibilities": task_def["taskDefinition"]["requiresCompatibilities"],
        "cpu": task_def["taskDefinition"]["cpu"],
        "memory": task_def["taskDefinition"]["memory"]
    }
    
    # Write to temp file
    with open("/tmp/task-def-lazy-init.json", "w") as f:
        json.dump(new_task_def, f, indent=2)
    
    # Register new task definition
    register_result = run_command(
        [
            "aws", "ecs", "register-task-definition",
            "--cli-input-json", f"file:///tmp/task-def-lazy-init.json",
            "--region", "us-east-1"
        ],
        "Register new task definition"
    )
    deployment_results["steps"].append({
        "step": "register_task_definition",
        "success": register_result["success"]
    })
    
    if not register_result["success"]:
        log("Failed to register new task definition", "ERROR")
        sys.exit(1)
    
    # Step 7: Update ECS service
    log("STEP 7: Updating ECS service")
    update_service_result = run_command(
        [
            "aws", "ecs", "update-service",
            "--cluster", "multimodal-lib-prod-cluster",
            "--service", "multimodal-lib-prod-service",
            "--task-definition", "multimodal-lib-prod-app",
            "--force-new-deployment",
            "--region", "us-east-1"
        ],
        "Update ECS service"
    )
    deployment_results["steps"].append({
        "step": "update_service",
        "success": update_service_result["success"]
    })
    
    if not update_service_result["success"]:
        log("Failed to update ECS service", "ERROR")
        sys.exit(1)
    
    # Step 8: Monitor deployment
    log("STEP 8: Monitoring deployment (waiting 2 minutes for stabilization)")
    log("You can monitor the deployment with:")
    log("  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    log("  python scripts/check-alb-health-status.py")
    
    time.sleep(120)  # Wait 2 minutes
    
    # Step 9: Check ALB health
    log("STEP 9: Checking ALB target health")
    health_check_result = run_command(
        ["python", "scripts/check-alb-health-status.py"],
        "ALB health check"
    )
    deployment_results["steps"].append({
        "step": "health_check",
        "success": health_check_result["success"]
    })
    
    # Save deployment results
    deployment_results["end_time"] = datetime.now().isoformat()
    deployment_results["overall_success"] = all(
        step["success"] for step in deployment_results["steps"]
    )
    
    output_file = f"lazy-init-fix-deployment-{int(time.time())}.json"
    with open(output_file, "w") as f:
        json.dump(deployment_results, f, indent=2)
    
    log(f"Deployment results saved to: {output_file}")
    
    if deployment_results["overall_success"]:
        log("=" * 80)
        log("DEPLOYMENT SUCCESSFUL!")
        log("=" * 80)
        log("The lazy initialization fix has been deployed.")
        log("Containers should now start quickly and pass health checks.")
        log("")
        log("Next steps:")
        log("1. Monitor container logs: aws logs tail /ecs/multimodal-lib-prod-app --follow")
        log("2. Check ALB health: python scripts/check-alb-health-status.py")
        log("3. Verify startup time is under 60 seconds")
        log("4. Test that routes work after databases initialize")
        return 0
    else:
        log("=" * 80)
        log("DEPLOYMENT FAILED", "ERROR")
        log("=" * 80)
        log("Some steps failed. Check the logs above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
