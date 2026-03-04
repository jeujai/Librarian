#!/usr/bin/env python3
"""
Monitor Task Definition 70 Health Status

Monitors the health status of tasks running with task definition 70
to verify the /health/simple endpoint is working correctly.
"""

import boto3
import time
from datetime import datetime

CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service-alb"
REGION = "us-east-1"

def check_task_health(ecs_client, cluster, service):
    """Check health status of running tasks"""
    # Get tasks for the service
    response = ecs_client.list_tasks(
        cluster=cluster,
        serviceName=service,
        desiredStatus='RUNNING'
    )
    
    task_arns = response['taskArns']
    
    if not task_arns:
        return None, "No running tasks found"
    
    # Describe tasks
    response = ecs_client.describe_tasks(
        cluster=cluster,
        tasks=task_arns
    )
    
    results = []
    for task in response['tasks']:
        task_id = task['taskArn'].split('/')[-1][:12]
        health_status = task.get('healthStatus', 'UNKNOWN')
        last_status = task.get('lastStatus', 'UNKNOWN')
        
        container = task['containers'][0]
        container_health = container.get('healthStatus', 'UNKNOWN')
        
        # Get task definition
        task_def = task['taskDefinitionArn'].split('/')[-1]
        
        results.append({
            'task_id': task_id,
            'task_def': task_def,
            'status': last_status,
            'health': health_status,
            'container_health': container_health
        })
    
    return results, None

def check_alb_target_health(elbv2_client):
    """Check ALB target group health"""
    try:
        # List target groups
        response = elbv2_client.describe_target_groups()
        
        for tg in response['TargetGroups']:
            if 'multimodal' in tg['TargetGroupName'].lower():
                tg_arn = tg['TargetGroupArn']
                tg_name = tg['TargetGroupName']
                
                # Get target health
                health_response = elbv2_client.describe_target_health(
                    TargetGroupArn=tg_arn
                )
                
                targets = health_response['TargetHealthDescriptions']
                if targets:
                    return tg_name, targets
        
        return None, []
    except Exception as e:
        return None, []

def main():
    print(f"\n{'='*70}")
    print("TASK DEFINITION 70 HEALTH MONITORING")
    print(f"{'='*70}")
    print(f"Monitoring health status for service: {SERVICE_NAME}")
    print(f"Health check endpoint: /health/simple")
    print(f"Start period: 5 minutes (300 seconds)")
    print(f"{'='*70}\n")
    
    ecs_client = boto3.client('ecs', region_name=REGION)
    elbv2_client = boto3.client('elbv2', region_name=REGION)
    
    start_time = time.time()
    check_count = 0
    last_health_status = None
    
    try:
        while check_count < 40:  # Monitor for ~10 minutes (40 checks * 15 seconds)
            check_count += 1
            elapsed = int(time.time() - start_time)
            
            # Check ECS task health
            tasks, error = check_task_health(ecs_client, CLUSTER_NAME, SERVICE_NAME)
            
            if error:
                print(f"[{elapsed}s] ⚠ {error}")
            elif tasks:
                for task in tasks:
                    status_line = (
                        f"[{elapsed}s] Task: {task['task_id']} | "
                        f"Def: {task['task_def']} | "
                        f"Status: {task['status']} | "
                        f"Health: {task['health']} | "
                        f"Container: {task['container_health']}"
                    )
                    
                    # Only print if status changed
                    if status_line != last_health_status:
                        print(status_line)
                        last_health_status = status_line
                    
                    # Check if healthy
                    if task['health'] == 'HEALTHY' and task['container_health'] == 'HEALTHY':
                        print(f"\n{'='*70}")
                        print("✓ TASK IS HEALTHY!")
                        print(f"{'='*70}")
                        print(f"Time to healthy: {elapsed} seconds ({elapsed/60:.1f} minutes)")
                        print(f"Task definition: {task['task_def']}")
                        print(f"Health check endpoint: /health/simple")
                        
                        # Check ALB target health
                        print(f"\n{'='*70}")
                        print("Checking ALB Target Health")
                        print(f"{'='*70}")
                        tg_name, targets = check_alb_target_health(elbv2_client)
                        
                        if tg_name and targets:
                            print(f"Target Group: {tg_name}")
                            for target in targets:
                                target_id = target['Target']['Id']
                                health_state = target['TargetHealth']['State']
                                print(f"  Target: {target_id} - State: {health_state}")
                        else:
                            print("  No target group information available")
                        
                        print(f"\n{'='*70}")
                        print("MONITORING COMPLETE")
                        print(f"{'='*70}\n")
                        return 0
            
            time.sleep(15)
        
        print(f"\n{'='*70}")
        print("Monitoring timeout reached (10 minutes)")
        print(f"{'='*70}")
        print("The task may still be starting up. Health check start period is 5 minutes.")
        print("Continue monitoring in AWS Console or run this script again.")
        print(f"{'='*70}\n")
        
    except KeyboardInterrupt:
        print(f"\n\nMonitoring stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ Error during monitoring: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
