#!/usr/bin/env python3
"""
Clean up unused target groups for multimodal-librarian project

This script identifies and removes target groups that are not being used
by any load balancers or ECS services.
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
            timeout=60
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

def get_target_groups():
    """Get all target groups related to the project."""
    cmd = """aws elbv2 describe-target-groups --region us-east-1 --query 'TargetGroups[?contains(TargetGroupName, `multimodal-lib-prod`) || contains(TargetGroupName, `ml-librarian-prod`)].{Name:TargetGroupName,Arn:TargetGroupArn,HealthCheckPath:HealthCheckPath}' --output json"""
    
    success, output = run_command(cmd, "Getting all target groups")
    if success:
        return json.loads(output)
    return []

def get_used_target_groups():
    """Get target groups that are currently in use."""
    used_target_groups = set()
    
    # Check ALB listeners
    alb_arns = [
        "arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb/f24be2cfb7f2f8ec",
        "arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-lib-prod-alb-v2/5964a1d711ab8dfe"
    ]
    
    for alb_arn in alb_arns:
        cmd = f"aws elbv2 describe-listeners --region us-east-1 --load-balancer-arn {alb_arn} --query 'Listeners[].DefaultActions[].TargetGroupArn' --output text"
        success, output = run_command(cmd, f"Getting target groups for ALB {alb_arn.split('/')[-2]}")
        if success and output.strip():
            for tg_arn in output.strip().split():
                if tg_arn != "None":
                    used_target_groups.add(tg_arn)
    
    # Check NLB listeners
    nlb_arn = "arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/net/multimodal-lib-prod-nlb/9f03ee5dda51903f"
    cmd = f"aws elbv2 describe-listeners --region us-east-1 --load-balancer-arn {nlb_arn} --query 'Listeners[].DefaultActions[].TargetGroupArn' --output text"
    success, output = run_command(cmd, "Getting target groups for NLB")
    if success and output.strip():
        for tg_arn in output.strip().split():
            if tg_arn != "None":
                used_target_groups.add(tg_arn)
    
    # Check ECS services
    cmd = "aws ecs describe-services --region us-east-1 --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service-alb --query 'services[0].loadBalancers[].targetGroupArn' --output text"
    success, output = run_command(cmd, "Getting target groups for ECS service")
    if success and output.strip() and output.strip() != "None":
        for tg_arn in output.strip().split():
            used_target_groups.add(tg_arn)
    
    return used_target_groups

def main():
    """Main execution function."""
    print("=" * 80)
    print("🧹 CLEANING UP UNUSED TARGET GROUPS")
    print("=" * 80)
    
    cleanup_log = {
        "timestamp": datetime.now().isoformat(),
        "operation": "cleanup_unused_target_groups",
        "target_groups_analyzed": [],
        "target_groups_deleted": [],
        "errors": []
    }
    
    # Step 1: Get all target groups
    print("\n📋 Step 1: Analyze Target Groups")
    all_target_groups = get_target_groups()
    
    if not all_target_groups:
        print("❌ Could not retrieve target groups. Aborting.")
        return False
    
    print(f"Found {len(all_target_groups)} target groups:")
    for tg in all_target_groups:
        print(f"  - {tg['Name']} ({tg['HealthCheckPath']})")
        cleanup_log["target_groups_analyzed"].append({
            "name": tg['Name'],
            "arn": tg['Arn'],
            "health_check_path": tg['HealthCheckPath']
        })
    
    # Step 2: Get used target groups
    print("\n📋 Step 2: Identify Used Target Groups")
    used_target_groups = get_used_target_groups()
    
    print(f"Found {len(used_target_groups)} target groups in use:")
    for tg_arn in used_target_groups:
        tg_name = tg_arn.split('/')[-2]
        print(f"  - {tg_name}")
    
    # Step 3: Identify unused target groups
    print("\n📋 Step 3: Identify Unused Target Groups")
    unused_target_groups = []
    
    for tg in all_target_groups:
        if tg['Arn'] not in used_target_groups:
            unused_target_groups.append(tg)
            print(f"  🗑️  UNUSED: {tg['Name']} ({tg['HealthCheckPath']})")
        else:
            print(f"  ✅ IN USE: {tg['Name']} ({tg['HealthCheckPath']})")
    
    if not unused_target_groups:
        print("\n🎉 No unused target groups found. Nothing to clean up!")
        return True
    
    # Step 4: Confirm deletion
    print(f"\n⚠️  Found {len(unused_target_groups)} unused target groups to delete:")
    for tg in unused_target_groups:
        print(f"  - {tg['Name']} (ARN: {tg['Arn']})")
    
    print("\n❓ Do you want to proceed with deletion? (y/N): ", end="")
    confirmation = input().strip().lower()
    
    if confirmation != 'y':
        print("❌ Deletion cancelled by user.")
        return False
    
    # Step 5: Delete unused target groups
    print("\n📋 Step 5: Delete Unused Target Groups")
    
    for tg in unused_target_groups:
        print(f"\n🗑️  Deleting target group: {tg['Name']}")
        
        # Check if target group has any registered targets first
        cmd = f"aws elbv2 describe-target-health --region us-east-1 --target-group-arn {tg['Arn']} --query 'TargetHealthDescriptions' --output json"
        success, output = run_command(cmd, f"Checking targets for {tg['Name']}")
        
        if success:
            targets = json.loads(output)
            if targets:
                print(f"⚠️  Target group {tg['Name']} has {len(targets)} registered targets. Deregistering first...")
                
                # Deregister targets
                for target in targets:
                    target_id = target['Target']['Id']
                    target_port = target['Target']['Port']
                    
                    deregister_cmd = f"aws elbv2 deregister-targets --region us-east-1 --target-group-arn {tg['Arn']} --targets Id={target_id},Port={target_port}"
                    success, _ = run_command(deregister_cmd, f"Deregistering target {target_id}:{target_port}")
                    
                    if not success:
                        cleanup_log["errors"].append(f"Failed to deregister target {target_id}:{target_port} from {tg['Name']}")
                
                # Wait for deregistration to complete
                print("⏳ Waiting 30 seconds for target deregistration...")
                time.sleep(30)
        
        # Delete the target group
        delete_cmd = f"aws elbv2 delete-target-group --region us-east-1 --target-group-arn {tg['Arn']}"
        success, output = run_command(delete_cmd, f"Deleting target group {tg['Name']}")
        
        if success:
            cleanup_log["target_groups_deleted"].append({
                "name": tg['Name'],
                "arn": tg['Arn'],
                "health_check_path": tg['HealthCheckPath']
            })
            print(f"✅ Successfully deleted target group: {tg['Name']}")
        else:
            cleanup_log["errors"].append(f"Failed to delete target group {tg['Name']}: {output}")
            print(f"❌ Failed to delete target group: {tg['Name']}")
    
    # Save cleanup log
    log_filename = f"target-group-cleanup-{int(time.time())}.json"
    with open(log_filename, 'w') as f:
        json.dump(cleanup_log, f, indent=2)
    
    print(f"\n📄 Cleanup log saved to: {log_filename}")
    
    # Summary
    print("\n" + "=" * 80)
    print("🎉 TARGET GROUP CLEANUP COMPLETED")
    print("=" * 80)
    print(f"✅ Target groups analyzed: {len(all_target_groups)}")
    print(f"✅ Target groups in use: {len(used_target_groups)}")
    print(f"🗑️  Target groups deleted: {len(cleanup_log['target_groups_deleted'])}")
    
    if cleanup_log["errors"]:
        print(f"⚠️  Errors encountered: {len(cleanup_log['errors'])}")
        for error in cleanup_log["errors"]:
            print(f"   - {error}")
    
    print(f"📄 Detailed log: {log_filename}")
    
    return len(cleanup_log["errors"]) == 0

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