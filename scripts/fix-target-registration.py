#!/usr/bin/env python3
"""
Fix ALB Target Registration

The issue: Target group has stale IP address from old task.
The solution: Force ECS service to re-register current task with ALB.
"""

import boto3
import json
import time
from datetime import datetime

def get_current_task_ip():
    """Get the current running task's IP address."""
    print("\n" + "="*80)
    print("STEP 1: Getting Current Task IP")
    print("="*80)
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    tasks = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service',
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return None
    
    task_arn = tasks['taskArns'][0]
    
    task_details = ecs.describe_tasks(
        cluster='multimodal-lib-prod-cluster',
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    task_ip = None
    
    for attachment in task.get('attachments', []):
        if attachment['type'] == 'ElasticNetworkInterface':
            for detail in attachment['details']:
                if detail['name'] == 'privateIPv4Address':
                    task_ip = detail['value']
    
    print(f"\n✅ Current Task:")
    print(f"   Task ARN: {task_arn}")
    print(f"   IP Address: {task_ip}")
    print(f"   Status: {task['lastStatus']}")
    
    return task_ip, task_arn

def get_target_group_targets():
    """Get current targets registered in target group."""
    print("\n" + "="*80)
    print("STEP 2: Checking Target Group Registration")
    print("="*80)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    tg_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/316aed9bcd042517'
    
    response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
    
    print(f"\n📋 Registered Targets:")
    for target in response['TargetHealthDescriptions']:
        ip = target['Target']['Id']
        port = target['Target']['Port']
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        
        print(f"   IP: {ip}:{port}")
        print(f"   State: {state}")
        print(f"   Reason: {reason}")
    
    return [t['Target']['Id'] for t in response['TargetHealthDescriptions']]

def force_service_update():
    """Force ECS service to update and re-register targets."""
    print("\n" + "="*80)
    print("STEP 3: Forcing Service Update")
    print("="*80)
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print(f"\n🔄 Forcing new deployment...")
    print(f"   This will cause ECS to re-register the task with the ALB")
    
    try:
        response = ecs.update_service(
            cluster='multimodal-lib-prod-cluster',
            service='multimodal-lib-prod-service',
            forceNewDeployment=True
        )
        
        print(f"✅ Service update initiated")
        print(f"   Deployment ID: {response['service']['deployments'][0]['id']}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to update service: {e}")
        return False

def monitor_target_registration(expected_ip, timeout=300):
    """Monitor target registration until correct IP is registered."""
    print("\n" + "="*80)
    print("STEP 4: Monitoring Target Registration")
    print("="*80)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    tg_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/316aed9bcd042517'
    
    print(f"\n⏱️  Monitoring for up to {timeout} seconds...")
    print(f"   Waiting for IP {expected_ip} to be registered")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < timeout:
        try:
            response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
            
            for target in response['TargetHealthDescriptions']:
                ip = target['Target']['Id']
                state = target['TargetHealth']['State']
                reason = target['TargetHealth'].get('Reason', 'N/A')
                
                if ip == expected_ip:
                    status_key = f"{ip}:{state}"
                    if status_key != last_status:
                        elapsed = int(time.time() - start_time)
                        print(f"\n[{elapsed}s] Target {ip}")
                        print(f"       State: {state}")
                        if reason != 'N/A':
                            print(f"       Reason: {reason}")
                        last_status = status_key
                    
                    if state == 'healthy':
                        print(f"\n✅ Target is HEALTHY!")
                        return True
            
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Error checking target health: {e}")
            time.sleep(10)
    
    print(f"\n⏱️  Monitoring timeout after {timeout} seconds")
    return False

def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("ALB TARGET REGISTRATION FIX")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'steps': {}
    }
    
    # Step 1: Get current task IP
    task_info = get_current_task_ip()
    if not task_info:
        print("\n❌ Cannot proceed without task information")
        return
    
    current_ip, task_arn = task_info
    results['current_task_ip'] = current_ip
    results['task_arn'] = task_arn
    
    # Step 2: Check target group
    registered_ips = get_target_group_targets()
    results['registered_ips'] = registered_ips
    
    if current_ip in registered_ips:
        print(f"\n✅ Current task IP is already registered")
        print(f"   The issue may be with the health check itself")
    else:
        print(f"\n❌ MISMATCH DETECTED!")
        print(f"   Current Task IP: {current_ip}")
        print(f"   Registered IPs: {registered_ips}")
        print(f"\n💡 This is why health checks are failing!")
    
    # Step 3: Force service update
    if force_service_update():
        results['service_update'] = 'success'
        
        # Step 4: Monitor registration
        if monitor_target_registration(current_ip, timeout=300):
            results['target_registration'] = 'healthy'
            results['status'] = 'success'
        else:
            results['target_registration'] = 'timeout'
            results['status'] = 'pending'
    else:
        results['service_update'] = 'failed'
        results['status'] = 'failed'
    
    # Save results
    output_file = f"target-registration-fix-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\n✅ Results saved to: {output_file}")
    
    if results['status'] == 'success':
        print("\n🎉 Target registration fixed successfully!")
        print(f"\n🌐 Your application should now be accessible at:")
        print(f"   https://d3a2xw711pvw5j.cloudfront.net/")
    elif results['status'] == 'pending':
        print("\n⏱️  Service update in progress")
        print("   Check status in a few minutes")
    else:
        print("\n❌ Target registration fix encountered issues")
        print("   Review the output above for details")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
