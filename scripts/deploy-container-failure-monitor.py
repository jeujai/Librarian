#!/usr/bin/env python3
"""
Deploy Container Failure Monitor Lambda

This script deploys the container failure monitoring Lambda function
using Terraform. It can be run standalone or as part of a larger deployment.
"""

import subprocess
import sys
import json
import argparse

def run_command(cmd, cwd=None):
    """Run a shell command and return output."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False, result.stderr
    
    return True, result.stdout

def deploy_lambda(alert_email=None, dry_run=False):
    """Deploy the container failure monitor Lambda."""
    
    print("=" * 80)
    print("DEPLOYING CONTAINER FAILURE MONITOR")
    print("=" * 80)
    print()
    
    terraform_dir = "infrastructure/aws-native"
    
    # Initialize Terraform
    print("1. Initializing Terraform...")
    success, output = run_command(
        ["terraform", "init"],
        cwd=terraform_dir
    )
    
    if not success:
        print("Failed to initialize Terraform")
        return False
    
    print("✓ Terraform initialized")
    print()
    
    # Plan deployment
    print("2. Planning deployment...")
    
    plan_cmd = ["terraform", "plan"]
    
    if alert_email:
        plan_cmd.extend([
            "-var", f"alert_email={alert_email}",
            "-var", "enable_container_failure_monitor=true"
        ])
    
    plan_cmd.extend([
        "-target", "module.monitoring.aws_lambda_function.container_failure_monitor",
        "-target", "module.monitoring.aws_sns_topic.container_failure_alerts",
        "-target", "module.monitoring.aws_cloudwatch_event_rule.container_failure_monitor",
        "-out", "container-monitor.tfplan"
    ])
    
    success, output = run_command(plan_cmd, cwd=terraform_dir)
    
    if not success:
        print("Failed to plan deployment")
        return False
    
    print("✓ Deployment plan created")
    print()
    
    if dry_run:
        print("Dry run complete - no changes applied")
        return True
    
    # Apply deployment
    print("3. Applying deployment...")
    
    success, output = run_command(
        ["terraform", "apply", "container-monitor.tfplan"],
        cwd=terraform_dir
    )
    
    if not success:
        print("Failed to apply deployment")
        return False
    
    print("✓ Deployment applied")
    print()
    
    # Get outputs
    print("4. Getting deployment outputs...")
    
    success, output = run_command(
        ["terraform", "output", "-json"],
        cwd=terraform_dir
    )
    
    if success:
        try:
            outputs = json.loads(output)
            
            print("Deployment Complete!")
            print("-" * 80)
            
            if "container_failure_monitor_function_arn" in outputs:
                function_arn = outputs["container_failure_monitor_function_arn"]["value"]
                print(f"Lambda Function ARN: {function_arn}")
            
            if "container_failure_alerts_topic_arn" in outputs:
                topic_arn = outputs["container_failure_alerts_topic_arn"]["value"]
                print(f"SNS Topic ARN: {topic_arn}")
                
                if alert_email:
                    print()
                    print(f"⚠️  Check your email ({alert_email}) to confirm SNS subscription")
            
            if "container_failure_monitor_log_group" in outputs:
                log_group = outputs["container_failure_monitor_log_group"]["value"]
                print(f"Log Group: {log_group}")
            
            print()
            print("Next Steps:")
            print("  1. Confirm SNS email subscription (if configured)")
            print("  2. Monitor Lambda logs for any issues")
            print("  3. Wait for first scheduled run (every 5 minutes)")
            print()
            print("To test manually:")
            print(f"  aws lambda invoke --function-name <function-name> output.json")
            
        except json.JSONDecodeError:
            print("Could not parse Terraform outputs")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Deploy container failure monitoring Lambda function'
    )
    parser.add_argument(
        '--email',
        help='Email address for alerts (optional)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Plan only, do not apply changes'
    )
    
    args = parser.parse_args()
    
    success = deploy_lambda(
        alert_email=args.email,
        dry_run=args.dry_run
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
