#!/usr/bin/env python3
"""
Fix ALB health check timeout by increasing timeout and adjusting thresholds
"""
import boto3
import json
from datetime import datetime

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def main():
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/316aed9bcd042517'
    
    log("=" * 80)
    log("Fixing ALB Health Check Configuration")
    log("=" * 80)
    
    # Get current configuration
    log("\nCurrent Configuration:")
    tg_resp = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
    tg = tg_resp['TargetGroups'][0]
    
    log(f"   Health Check Path: {tg['HealthCheckPath']}")
    log(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    log(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    log(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
    log(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    # Update configuration with more lenient settings
    log("\nUpdating to more lenient configuration...")
    log("   - Increasing timeout to 29 seconds (max for 30s interval)")
    log("   - Keeping interval at 30 seconds")
    log("   - Reducing unhealthy threshold to 2 (faster detection)")
    log("   - Keeping healthy threshold at 2")
    
    elbv2.modify_target_group(
        TargetGroupArn=target_group_arn,
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=29,  # Max allowed for 30s interval
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=2,  # Faster unhealthy detection
        Matcher={'HttpCode': '200,201'}
    )
    
    log("\n✓ Health check configuration updated successfully!")
    
    # Verify new configuration
    log("\nNew Configuration:")
    tg_resp = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
    tg = tg_resp['TargetGroups'][0]
    
    log(f"   Health Check Path: {tg['HealthCheckPath']}")
    log(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    log(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    log(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
    log(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    log("\n" + "=" * 80)
    log("Configuration Update Complete")
    log("=" * 80)
    log("\nThe ALB will now wait up to 29 seconds for health check responses.")
    log("Monitor target health with:")
    log("  aws elbv2 describe-target-health --target-group-arn " + target_group_arn)

if __name__ == '__main__':
    main()
