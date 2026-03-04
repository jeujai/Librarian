#!/usr/bin/env python3
"""
Fix ALB connectivity to port 8000 by ensuring the application listens on 0.0.0.0:8000
and adjusting health check settings.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ecs = boto3.client('ecs')
    elbv2 = boto3.client('elbv2')
    
    cluster_name = 'multimodal-librarian-cluster'
    
    print("=" * 80)
    print("ALB Port 8000 Connectivity Fix")
    print("=" * 80)
    
    # Step 1: Check target group health check settings
    print("\n1. Checking target group health check settings...")
    tg_response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg-v2']
    )
    
    if tg_response['TargetGroups']:
        tg = tg_response['TargetGroups'][0]
        tg_arn = tg['TargetGroupArn']
        
        print(f"   Target Group: {tg['TargetGroupName']}")
        print(f"   Health Check Path: {tg['HealthCheckPath']}")
        print(f"   Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
        print(f"   Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
        print(f"   Healthy Threshold: {tg['HealthyThresholdCount']}")
        print(f"   Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
        
        # Step 2: Increase health check timeout and interval
        print("\n2. Updating health check settings for better reliability...")
        elbv2.modify_target_group(
            TargetGroupArn=tg_arn,
            HealthCheckEnabled=True,
            HealthCheckPath='/health/simple',
            HealthCheckIntervalSeconds=30,  # Check every 30 seconds
            HealthCheckTimeoutSeconds=10,   # Wait up to 10 seconds
            HealthyThresholdCount=2,        # 2 successful checks = healthy
            UnhealthyThresholdCount=3,      # 3 failed checks = unhealthy
            Matcher={'HttpCode': '200'}
        )
        print("   ✓ Health check settings updated")
        
        # Step 3: Check current target health
        print("\n3. Checking current target health...")
        health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        
        for target in health_response['TargetHealthDescriptions']:
            ip = target['Target']['Id']
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            print(f"   Target {ip}: {state} ({reason})")
    
    # Step 4: Check task definition to ensure it binds to 0.0.0.0
    print("\n4. Checking task definition port bindings...")
    services = ecs.list_services(cluster=cluster_name)
    
    if services['serviceArns']:
        service_arn = services['serviceArns'][0]
        service_desc = ecs.describe_services(
            cluster=cluster_name,
            services=[service_arn]
        )
        
        if service_desc['services']:
            service = service_desc['services'][0]
            task_def_arn = service['taskDefinition']
            
            task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
            container_def = task_def['taskDefinition']['containerDefinitions'][0]
            
            print(f"   Task Definition: {task_def_arn.split('/')[-1]}")
            print(f"   Container: {container_def['name']}")
            
            # Check port mappings
            if 'portMappings' in container_def:
                for port_mapping in container_def['portMappings']:
                    print(f"   Port Mapping: {port_mapping}")
            
            # Check command/entrypoint
            if 'command' in container_def:
                print(f"   Command: {' '.join(container_def['command'])}")
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)
    print("\nThe issue is likely one of the following:")
    print("1. Application not binding to 0.0.0.0:8000 (only localhost)")
    print("2. Health check timing out before application responds")
    print("3. Application not starting fast enough")
    print("\nRECOMMENDED ACTIONS:")
    print("1. Ensure your application binds to 0.0.0.0:8000, not 127.0.0.1:8000")
    print("2. Check application logs for startup errors")
    print("3. Verify /health/simple endpoint responds quickly (<10s)")
    print("4. Consider increasing container memory if OOM issues")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'target_group': tg['TargetGroupName'] if tg_response['TargetGroups'] else None,
        'health_check_settings': {
            'path': tg['HealthCheckPath'],
            'interval': tg['HealthCheckIntervalSeconds'],
            'timeout': tg['HealthCheckTimeoutSeconds']
        } if tg_response['TargetGroups'] else None,
        'target_health': health_response['TargetHealthDescriptions'] if tg_response['TargetGroups'] else []
    }
    
    filename = f'alb-port-8000-diagnosis-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

if __name__ == '__main__':
    main()
