#!/usr/bin/env python3
"""
Update ECS Service with New Target Group

This script updates the ECS service to use the new target group created in Task 1,
forces a new deployment, and monitors the deployment progress.
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
CONTAINER_NAME = "multimodal-lib-prod-app"
CONTAINER_PORT = 8000
HEALTH_CHECK_GRACE_PERIOD = 300  # 5 minutes
TARGET_GROUP_ARN = "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34"

# Initialize AWS clients
ecs_client = boto3.client('ecs', region_name='us-east-1')
elbv2_client = boto3.client('elbv2', region_name='us-east-1')


def get_current_service_config() -> Dict[str, Any]:
    """Get current ECS service configuration."""
    print("📋 Getting current service configuration...")
    
    response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not response['services']:
        raise Exception(f"Service {SERVICE_NAME} not found in cluster {CLUSTER_NAME}")
    
    service = response['services'][0]
    print(f"✅ Current service status: {service['status']}")
    print(f"   Running tasks: {service['runningCount']}")
    print(f"   Desired tasks: {service['desiredCount']}")
    
    return service


def update_ecs_service() -> Dict[str, Any]:
    """Update ECS service with new target group."""
    print(f"\n🔄 Updating ECS service with new target group...")
    print(f"   Target Group ARN: {TARGET_GROUP_ARN}")
    
    try:
        response = ecs_client.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            loadBalancers=[
                {
                    'targetGroupArn': TARGET_GROUP_ARN,
                    'containerName': CONTAINER_NAME,
                    'containerPort': CONTAINER_PORT
                }
            ],
            healthCheckGracePeriodSeconds=HEALTH_CHECK_GRACE_PERIOD,
            forceNewDeployment=True
        )
        
        service = response['service']
        print(f"✅ Service update initiated successfully")
        print(f"   Service ARN: {service['serviceArn']}")
        print(f"   Deployment ID: {service['deployments'][0]['id']}")
        
        return service
        
    except Exception as e:
        print(f"❌ Error updating service: {str(e)}")
        raise


def monitor_deployment(timeout_minutes: int = 15) -> bool:
    """Monitor the deployment progress."""
    print(f"\n👀 Monitoring deployment (timeout: {timeout_minutes} minutes)...")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    check_interval = 10  # seconds
    
    while time.time() - start_time < timeout_seconds:
        try:
            # Get service status
            response = ecs_client.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            service = response['services'][0]
            deployments = service['deployments']
            
            # Show current status
            print(f"\n⏱️  Time elapsed: {int(time.time() - start_time)}s")
            print(f"   Running: {service['runningCount']}, Desired: {service['desiredCount']}")
            
            # Show deployment status
            for i, deployment in enumerate(deployments):
                status = deployment['status']
                running = deployment['runningCount']
                desired = deployment['desiredCount']
                print(f"   Deployment {i+1}: {status} (Running: {running}/{desired})")
            
            # Show recent events
            if service.get('events'):
                print(f"\n   Recent events:")
                for event in service['events'][:3]:
                    timestamp = event['createdAt'].strftime('%H:%M:%S')
                    message = event['message']
                    print(f"   [{timestamp}] {message}")
            
            # Check if deployment is complete
            if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
                primary = deployments[0]
                if primary['runningCount'] == primary['desiredCount']:
                    print(f"\n✅ Deployment completed successfully!")
                    return True
            
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"⚠️  Error monitoring deployment: {str(e)}")
            time.sleep(check_interval)
    
    print(f"\n⏰ Deployment monitoring timed out after {timeout_minutes} minutes")
    return False


def check_target_health() -> Dict[str, Any]:
    """Check the health of targets in the target group."""
    print(f"\n🏥 Checking target health...")
    
    try:
        response = elbv2_client.describe_target_health(
            TargetGroupArn=TARGET_GROUP_ARN
        )
        
        targets = response['TargetHealthDescriptions']
        
        if not targets:
            print("⚠️  No targets registered yet")
            return {'healthy': 0, 'total': 0, 'targets': []}
        
        healthy_count = 0
        target_info = []
        
        for target in targets:
            target_id = target['Target']['Id']
            port = target['Target']['Port']
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            
            target_info.append({
                'id': target_id,
                'port': port,
                'state': state,
                'reason': reason
            })
            
            if state == 'healthy':
                healthy_count += 1
                print(f"   ✅ Target {target_id}:{port} - {state}")
            elif state == 'initial':
                print(f"   🔄 Target {target_id}:{port} - {state} (registering)")
            else:
                print(f"   ⚠️  Target {target_id}:{port} - {state} ({reason})")
        
        print(f"\n   Summary: {healthy_count}/{len(targets)} targets healthy")
        
        return {
            'healthy': healthy_count,
            'total': len(targets),
            'targets': target_info
        }
        
    except Exception as e:
        print(f"❌ Error checking target health: {str(e)}")
        return {'healthy': 0, 'total': 0, 'targets': [], 'error': str(e)}


def wait_for_healthy_targets(timeout_minutes: int = 10) -> bool:
    """Wait for targets to become healthy."""
    print(f"\n⏳ Waiting for targets to become healthy (timeout: {timeout_minutes} minutes)...")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    check_interval = 15  # seconds
    
    while time.time() - start_time < timeout_seconds:
        health_status = check_target_health()
        
        if health_status['total'] > 0 and health_status['healthy'] == health_status['total']:
            print(f"\n✅ All targets are healthy!")
            return True
        
        elapsed = int(time.time() - start_time)
        print(f"\n   ⏱️  Waiting... ({elapsed}s elapsed)")
        time.sleep(check_interval)
    
    print(f"\n⏰ Timeout waiting for healthy targets after {timeout_minutes} minutes")
    return False


def get_task_details() -> List[Dict[str, Any]]:
    """Get details of running tasks."""
    print(f"\n📦 Getting task details...")
    
    try:
        # List tasks
        list_response = ecs_client.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='RUNNING'
        )
        
        if not list_response['taskArns']:
            print("⚠️  No running tasks found")
            return []
        
        # Describe tasks
        describe_response = ecs_client.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=list_response['taskArns']
        )
        
        tasks_info = []
        for task in describe_response['tasks']:
            task_id = task['taskArn'].split('/')[-1]
            status = task['lastStatus']
            health = task.get('healthStatus', 'UNKNOWN')
            
            # Get task IP
            task_ip = None
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'privateIPv4Address':
                            task_ip = detail['value']
                            break
            
            task_info = {
                'id': task_id,
                'status': status,
                'health': health,
                'ip': task_ip
            }
            
            tasks_info.append(task_info)
            print(f"   Task {task_id[:8]}... - Status: {status}, Health: {health}, IP: {task_ip}")
        
        return tasks_info
        
    except Exception as e:
        print(f"❌ Error getting task details: {str(e)}")
        return []


def save_results(results: Dict[str, Any]) -> str:
    """Save results to JSON file."""
    timestamp = int(time.time())
    filename = f"ecs-service-update-{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {filename}")
    return filename


def main():
    """Main execution function."""
    print("=" * 80)
    print("ECS Service Update with New Target Group")
    print("=" * 80)
    
    results = {
        'success': False,
        'timestamp': datetime.now().isoformat(),
        'cluster': CLUSTER_NAME,
        'service': SERVICE_NAME,
        'target_group_arn': TARGET_GROUP_ARN
    }
    
    try:
        # Step 1: Get current service config
        current_service = get_current_service_config()
        results['previous_config'] = {
            'status': current_service['status'],
            'running_count': current_service['runningCount'],
            'desired_count': current_service['desiredCount']
        }
        
        # Step 2: Update service
        updated_service = update_ecs_service()
        results['service_updated'] = True
        results['deployment_id'] = updated_service['deployments'][0]['id']
        
        # Step 3: Monitor deployment
        deployment_success = monitor_deployment(timeout_minutes=15)
        results['deployment_completed'] = deployment_success
        
        if not deployment_success:
            print("\n⚠️  Deployment did not complete within timeout, but may still be in progress")
            print("   Check AWS Console or run monitoring commands manually")
        
        # Step 4: Get task details
        tasks = get_task_details()
        results['tasks'] = tasks
        
        # Step 5: Check target health
        health_status = check_target_health()
        results['target_health'] = health_status
        
        # Step 6: Wait for healthy targets
        if health_status['total'] > 0:
            targets_healthy = wait_for_healthy_targets(timeout_minutes=10)
            results['targets_healthy'] = targets_healthy
            
            if targets_healthy:
                results['success'] = True
                print("\n" + "=" * 80)
                print("✅ SUCCESS: ECS service updated and targets are healthy!")
                print("=" * 80)
            else:
                print("\n" + "=" * 80)
                print("⚠️  WARNING: Targets not yet healthy, but update completed")
                print("   Targets may still be initializing. Check again in a few minutes.")
                print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print("⚠️  WARNING: No targets registered yet")
            print("   Wait for tasks to fully start and register with target group")
            print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error during execution: {str(e)}")
        results['error'] = str(e)
        import traceback
        results['traceback'] = traceback.format_exc()
    
    finally:
        # Save results
        filename = save_results(results)
        
        # Print summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Service Updated: {results.get('service_updated', False)}")
        print(f"Deployment Completed: {results.get('deployment_completed', False)}")
        print(f"Targets Healthy: {results.get('targets_healthy', False)}")
        print(f"Overall Success: {results['success']}")
        print(f"Results saved to: {filename}")
        print("=" * 80)
    
    return 0 if results['success'] else 1


if __name__ == "__main__":
    sys.exit(main())
