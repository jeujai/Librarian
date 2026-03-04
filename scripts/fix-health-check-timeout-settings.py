#!/usr/bin/env python3
"""
Fix health check timeout settings to allow application more time to start.
"""

import boto3
import time

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TARGET_GROUP_ARN = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34'

ecs = boto3.client('ecs', region_name=REGION)
elbv2 = boto3.client('elbv2', region_name=REGION)

def update_target_group_health_check():
    """Update target group health check settings"""
    print("=" * 70)
    print("UPDATING TARGET GROUP HEALTH CHECK SETTINGS")
    print("=" * 70)
    
    print("\n🔧 Current settings:")
    tg = elbv2.describe_target_groups(TargetGroupArns=[TARGET_GROUP_ARN])['TargetGroups'][0]
    print(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    print(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    print(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
    print(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    print("\n🔧 Updating to more lenient settings...")
    print("   Health Check Interval: 30s → 30s (no change)")
    print("   Health Check Timeout: 29s → 29s (max allowed)")
    print("   Healthy Threshold: 2 → 2 (no change)")
    print("   Unhealthy Threshold: 2 → 5 (more tolerant)")
    
    response = elbv2.modify_target_group(
        TargetGroupArn=TARGET_GROUP_ARN,
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=29,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=5  # More tolerant
    )
    
    print("   ✅ Target group updated")

def update_ecs_health_check_grace_period():
    """Update ECS service health check grace period"""
    print("\n" + "=" * 70)
    print("UPDATING ECS HEALTH CHECK GRACE PERIOD")
    print("=" * 70)
    
    print("\n🔧 Increasing health check grace period to 300 seconds (5 minutes)")
    print("   This gives the application time to start up before health checks begin")
    
    response = ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        healthCheckGracePeriodSeconds=300,  # 5 minutes
        forceNewDeployment=True
    )
    
    print("   ✅ Service updated with 300s grace period")
    print("   ✅ New deployment initiated")

def main():
    print("=" * 70)
    print("FIX HEALTH CHECK TIMEOUT SETTINGS")
    print("=" * 70)
    
    try:
        # Update target group
        update_target_group_health_check()
        
        # Update ECS service
        update_ecs_health_check_grace_period()
        
        print("\n" + "=" * 70)
        print("✅ HEALTH CHECK SETTINGS UPDATED")
        print("=" * 70)
        print("\n📊 Summary:")
        print("   • Target Group: More tolerant unhealthy threshold (5)")
        print("   • ECS Service: 300s health check grace period")
        print("   • Deployment: New deployment initiated")
        print("\n🔗 Next steps:")
        print("   1. Wait 5-10 minutes for deployment")
        print("   2. Check target health")
        print("   3. Verify application logs")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
