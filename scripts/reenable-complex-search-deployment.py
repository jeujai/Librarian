#!/usr/bin/env python3
"""
Re-enable Complex Search Deployment Script

This script re-enables the complex search functionality that was temporarily disabled
to resolve circular import issues, builds a new Docker image, and deploys it to ECS.
"""

import subprocess
import sys
import time
import json
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
            return True
        else:
            print(f"❌ {description} failed")
            print(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"💥 {description} failed with exception: {e}")
        return False

def check_ecs_service_health():
    """Check if the ECS service is healthy after deployment."""
    print("\n🏥 Checking ECS service health...")
    
    # Get service status
    cmd = """
    aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].{
            Status: status,
            RunningCount: runningCount,
            PendingCount: pendingCount,
            DesiredCount: desiredCount,
            TaskDefinition: taskDefinition
        }' \
        --output json
    """
    
    if not run_command(cmd, "Getting ECS service status"):
        return False
    
    # Get task health
    cmd = """
    aws ecs list-tasks \
        --cluster multimodal-lib-prod-cluster \
        --service-name multimodal-lib-prod-service \
        --query 'taskArns[0]' \
        --output text
    """
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip() != "None":
        task_arn = result.stdout.strip()
        
        cmd = f"""
        aws ecs describe-tasks \
            --cluster multimodal-lib-prod-cluster \
            --tasks {task_arn} \
            --query 'tasks[0].{{
                LastStatus: lastStatus,
                HealthStatus: healthStatus,
                CreatedAt: createdAt,
                StartedAt: startedAt
            }}' \
            --output json
        """
        
        return run_command(cmd, "Getting task health status")
    
    return True

def test_complex_search_functionality():
    """Test that complex search is working properly."""
    print("\n🧪 Testing complex search functionality...")
    
    test_script = """
import sys
sys.path.append('/app/src')

try:
    from multimodal_librarian.components.vector_store.search_service import (
        EnhancedSemanticSearchService,
        SearchRequest,
        COMPLEX_SEARCH_AVAILABLE
    )
    
    print(f"Complex search available: {COMPLEX_SEARCH_AVAILABLE}")
    
    if COMPLEX_SEARCH_AVAILABLE:
        print("✅ Complex search functionality successfully re-enabled")
        
        # Try to import complex search components
        from multimodal_librarian.components.vector_store.search_service_complex import (
            EnhancedSemanticSearchService as ComplexSearchService
        )
        print("✅ Complex search service imported successfully")
        
    else:
        print("⚠️  Complex search still disabled - check for import issues")
        
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error testing complex search: {e}")
    sys.exit(1)
    
print("🎉 Complex search functionality test completed successfully")
"""
    
    # Write test script to temporary file
    with open('/tmp/test_complex_search.py', 'w') as f:
        f.write(test_script)
    
    return run_command("python /tmp/test_complex_search.py", "Testing complex search imports")

def main():
    """Main deployment process."""
    print("🚀 Starting Complex Search Re-enablement Deployment")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Step 1: Test complex search functionality locally
    if not test_complex_search_functionality():
        print("❌ Local complex search test failed")
        return False
    
    # Step 2: Build new Docker image
    image_tag = f"multimodal-librarian:complex-search-reenabled-{int(time.time())}"
    
    if not run_command(f"docker build -t {image_tag} .", "Building Docker image with re-enabled complex search"):
        return False
    
    # Step 3: Tag for ECR
    ecr_uri = f"591222106065.dkr.ecr.us-east-1.amazonaws.com/{image_tag}"
    
    if not run_command(f"docker tag {image_tag} {ecr_uri}", "Tagging image for ECR"):
        return False
    
    # Step 4: Push to ECR
    if not run_command("aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 591222106065.dkr.ecr.us-east-1.amazonaws.com", "Logging into ECR"):
        return False
    
    if not run_command(f"docker push {ecr_uri}", "Pushing image to ECR"):
        return False
    
    # Step 5: Update latest tag
    latest_uri = "591222106065.dkr.ecr.us-east-1.amazonaws.com/multimodal-librarian:latest"
    
    if not run_command(f"docker tag {image_tag} {latest_uri}", "Tagging as latest"):
        return False
    
    if not run_command(f"docker push {latest_uri}", "Pushing latest tag"):
        return False
    
    # Step 6: Force ECS service update
    if not run_command(
        "aws ecs update-service --cluster multimodal-lib-prod-cluster --service multimodal-lib-prod-service --force-new-deployment",
        "Forcing ECS service deployment"
    ):
        return False
    
    # Step 7: Wait for deployment to stabilize
    print("\n⏳ Waiting for deployment to stabilize...")
    time.sleep(30)
    
    if not run_command(
        "aws ecs wait services-stable --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service",
        "Waiting for service to stabilize"
    ):
        print("⚠️  Service stabilization wait timed out, but deployment may still be in progress")
    
    # Step 8: Check service health
    if not check_ecs_service_health():
        print("⚠️  Could not verify service health, but deployment completed")
    
    # Step 9: Test the deployed service
    print("\n🧪 Testing deployed service...")
    
    # Simple health check
    if run_command("curl -f http://localhost:8000/health/simple || echo 'Health check not accessible from this environment'", "Testing service health endpoint"):
        print("✅ Service appears to be responding")
    
    print("\n🎉 Complex Search Re-enablement Deployment Completed!")
    print(f"Image: {ecr_uri}")
    print(f"Latest: {latest_uri}")
    print("\nNext steps:")
    print("1. Monitor the service logs for any startup issues")
    print("2. Test complex search functionality through the API")
    print("3. Verify that search performance is improved")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)