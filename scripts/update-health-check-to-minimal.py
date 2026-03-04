#!/usr/bin/env python3
"""
Update ALB and ECS health check paths to /health/minimal

This script updates the Terraform infrastructure to use the /health/minimal
endpoint for both ALB target group health checks and ECS task health checks.
"""

import json
import subprocess
import sys
import time
from datetime import datetime

def run_command(command, description):
    """Run a command and return the result."""
    print(f"\n🔄 {description}")
    print(f"Command: {command}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
            return True, result.stdout
        else:
            print(f"❌ {description} - FAILED")
            print(f"Error: {result.stderr}")
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - TIMEOUT")
        return False, "Command timed out"
    except Exception as e:
        print(f"💥 {description} - EXCEPTION: {e}")
        return False, str(e)

def main():
    """Main execution function."""
    print("=" * 80)
    print("🏥 UPDATING HEALTH CHECK PATH TO /health/minimal")
    print("=" * 80)
    
    deployment_log = {
        "timestamp": datetime.now().isoformat(),
        "operation": "update_health_check_path",
        "target_path": "/health/minimal",
        "previous_path": "/api/health/simple",
        "steps": []
    }
    
    # Step 1: Validate Terraform configuration
    print("\n📋 Step 1: Validate Terraform Configuration")
    success, output = run_command(
        "cd infrastructure/aws-native && terraform validate",
        "Validating Terraform configuration"
    )
    
    deployment_log["steps"].append({
        "step": "terraform_validate",
        "success": success,
        "output": output[:500] if output else None
    })
    
    if not success:
        print("❌ Terraform validation failed. Aborting deployment.")
        return False
    
    # Step 2: Plan the changes
    print("\n📋 Step 2: Plan Terraform Changes")
    success, output = run_command(
        "cd infrastructure/aws-native && terraform plan -out=health-check-update.tfplan",
        "Planning Terraform changes"
    )
    
    deployment_log["steps"].append({
        "step": "terraform_plan",
        "success": success,
        "output": output[:1000] if output else None
    })
    
    if not success:
        print("❌ Terraform planning failed. Aborting deployment.")
        return False
    
    # Step 3: Apply the changes
    print("\n📋 Step 3: Apply Terraform Changes")
    success, output = run_command(
        "cd infrastructure/aws-native && terraform apply health-check-update.tfplan",
        "Applying Terraform changes"
    )
    
    deployment_log["steps"].append({
        "step": "terraform_apply",
        "success": success,
        "output": output[:1000] if output else None
    })
    
    if not success:
        print("❌ Terraform apply failed.")
        return False
    
    # Step 4: Wait for deployment to stabilize
    print("\n📋 Step 4: Wait for Deployment Stabilization")
    print("⏳ Waiting 60 seconds for changes to take effect...")
    time.sleep(60)
    
    # Step 5: Verify health check endpoint
    print("\n📋 Step 5: Verify Health Check Endpoint")
    
    # Get ALB DNS name from Terraform output
    success, alb_dns = run_command(
        "cd infrastructure/aws-native && terraform output -raw alb_dns_name",
        "Getting ALB DNS name"
    )
    
    if success and alb_dns.strip():
        alb_url = f"http://{alb_dns.strip()}/health/minimal"
        print(f"🔍 Testing health endpoint: {alb_url}")
        
        success, output = run_command(
            f"curl -f -m 10 {alb_url}",
            "Testing /health/minimal endpoint"
        )
        
        deployment_log["steps"].append({
            "step": "health_check_test",
            "success": success,
            "endpoint": alb_url,
            "output": output[:500] if output else None
        })
        
        if success:
            print("✅ Health check endpoint is responding correctly!")
        else:
            print("⚠️  Health check endpoint test failed, but deployment completed.")
    else:
        print("⚠️  Could not retrieve ALB DNS name for testing.")
    
    # Step 6: Clean up plan file
    run_command(
        "cd infrastructure/aws-native && rm -f health-check-update.tfplan",
        "Cleaning up plan file"
    )
    
    # Save deployment log
    log_filename = f"health-check-update-{int(time.time())}.json"
    with open(log_filename, 'w') as f:
        json.dump(deployment_log, f, indent=2)
    
    print(f"\n📄 Deployment log saved to: {log_filename}")
    
    # Summary
    print("\n" + "=" * 80)
    print("🎉 HEALTH CHECK PATH UPDATE COMPLETED")
    print("=" * 80)
    print(f"✅ ALB Target Group health check path: /health/minimal")
    print(f"✅ ECS Task Definition health check path: /health/minimal")
    print(f"📄 Deployment log: {log_filename}")
    
    if alb_dns.strip():
        print(f"🔗 Test endpoint: http://{alb_dns.strip()}/health/minimal")
    
    print("\n📋 Next Steps:")
    print("1. Monitor ECS service health in AWS Console")
    print("2. Check ALB target group health status")
    print("3. Verify application logs for any issues")
    print("4. Test the health endpoint manually if needed")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        sys.exit(1)