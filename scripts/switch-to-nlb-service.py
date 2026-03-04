#!/usr/bin/env python3
"""
Switch ECS Service to NLB
==========================

This script properly switches the ECS service to use the NLB by:
1. Scaling down the current service to 0
2. Deleting the old service
3. Creating a new service with NLB configuration

Usage:
    python scripts/switch-to-nlb-service.py
"""

import boto3
import json
import time
from datetime import datetime
from typing import Dict, Any

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
OLD_SERVICE_NAME = "multimodal-lib-prod-service"
NEW_SERVICE_NAME = "multimodal-lib-prod-service"
TASK_DEFINITION = "multimodal-lib-prod-app"
NLB_TARGET_GROUP_ARN = "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-nlb-tg/e3896922f939759a"
CONTAINER_NAME = "multimodal-lib-prod-app"
CONTAINER_PORT = 8000

# Subnets and security groups
SUBNETS = [
    "subnet-0c352188f5398a718",
    "subnet-02f4d9ecb751beb27",
    "subnet-02fe694f061238d5a"
]
SECURITY_GROUPS = ["sg-0135b368e20b7bd01"]

# Initialize AWS clients
ecs_client = boto3.client('ecs', region_name='us-east-1')
elbv2_client = boto3.client('elbv2', region_name='us-east-1')


def get_current_task_definition() -> str:
    """Get the current task definition ARN."""
    print("\n" + "="*80)
    print("Getting Current Task Definition")
    print("="*80)
    
    try:
        response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[OLD_SERVICE_NAME]
        )
        
        service = response['services'][0]
        task_def_arn = service['taskDefinition']
        
        print(f"✅ Current Task Definition: {task_def_arn}")
        return task_def_arn
        
    except Exception as e:
        print(f"❌ Error getting task definition: {str(e)}")
        raise


def scale_down_service() -> bool:
    """Scale down the current service to 0."""
    print("\n" + "="*80)
    print("STEP 1: Scaling Down Current Service")
    print("="*80)
    
    try:
        response = ecs_client.update_service(
            cluster=CLUSTER_NAME,
            service=OLD_SERVICE_NAME,
            desiredCount=0
        )
        
        print(f"✅ Service scaled down to 0")
        print(f"   Waiting for tasks to stop...")
        
        # Wait for tasks to stop
        max_wait = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = ecs_client.describe_services(
                cluster=CLUSTER_NAME,
                services=[OLD_SERVICE_NAME]
            )
            
            service = response['services'][0]
            running_count = service['runningCount']
            
            if running_count == 0:
                print(f"✅ All tasks stopped")
                return True
            
            print(f"   ⏳ Running tasks: {running_count}")
            time.sleep(10)
        
        print(f"⚠️  Timeout waiting for tasks to stop")
        return False
        
    except Exception as e:
        print(f"❌ Error scaling down service: {str(e)}")
        raise


def delete_old_service() -> bool:
    """Delete the old service."""
    print("\n" + "="*80)
    print("STEP 2: Deleting Old Service")
    print("="*80)
    
    try:
        response = ecs_client.delete_service(
            cluster=CLUSTER_NAME,
            service=OLD_SERVICE_NAME,
            force=True
        )
        
        print(f"✅ Service deletion initiated")
        print(f"   Waiting for service to be deleted...")
        
        # Wait for service to be deleted
        max_wait = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                response = ecs_client.describe_services(
                    cluster=CLUSTER_NAME,
                    services=[OLD_SERVICE_NAME]
                )
                
                service = response['services'][0]
                status = service['status']
                
                if status == 'INACTIVE':
                    print(f"✅ Service deleted successfully")
                    return True
                
                print(f"   ⏳ Service status: {status}")
                time.sleep(10)
                
            except Exception:
                # Service not found means it's deleted
                print(f"✅ Service deleted successfully")
                return True
        
        print(f"⚠️  Timeout waiting for service deletion")
        return False
        
    except Exception as e:
        print(f"❌ Error deleting service: {str(e)}")
        raise


def create_new_service_with_nlb(task_def_arn: str) -> Dict[str, Any]:
    """Create new service with NLB configuration."""
    print("\n" + "="*80)
    print("STEP 3: Creating New Service with NLB")
    print("="*80)
    
    try:
        response = ecs_client.create_service(
            cluster=CLUSTER_NAME,
            serviceName=NEW_SERVICE_NAME,
            taskDefinition=task_def_arn,
            loadBalancers=[
                {
                    'targetGroupArn': NLB_TARGET_GROUP_ARN,
                    'containerName': CONTAINER_NAME,
                    'containerPort': CONTAINER_PORT
                }
            ],
            desiredCount=1,
            launchType='FARGATE',
            platformVersion='LATEST',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': SUBNETS,
                    'securityGroups': SECURITY_GROUPS,
                    'assignPublicIp': 'ENABLED'
                }
            },
            healthCheckGracePeriodSeconds=300,
            deploymentConfiguration={
                'maximumPercent': 200,
                'minimumHealthyPercent': 100,
                'deploymentCircuitBreaker': {
                    'enable': True,
                    'rollback': True
                }
            },
            tags=[
                {'key': 'Name', 'value': NEW_SERVICE_NAME},
                {'key': 'Environment', 'value': 'production'},
                {'key': 'Application', 'value': 'multimodal-librarian'},
                {'key': 'LoadBalancer', 'value': 'NLB'},
                {'key': 'CreatedDate', 'value': datetime.now().isoformat()}
            ]
        )
        
        service = response['service']
        
        print(f"✅ New Service Created Successfully!")
        print(f"   Service: {service['serviceName']}")
        print(f"   Status: {service['status']}")
        print(f"   Desired Count: {service['desiredCount']}")
        print(f"   Load Balancer: NLB")
        print(f"   Target Group: {NLB_TARGET_GROUP_ARN}")
        
        return {
            'ServiceName': service['serviceName'],
            'ServiceArn': service['serviceArn'],
            'Status': service['status'],
            'Details': service
        }
        
    except Exception as e:
        print(f"❌ Error creating service: {str(e)}")
        raise


def monitor_service_startup(duration_seconds: int = 600) -> bool:
    """Monitor service startup and target health."""
    print("\n" + "="*80)
    print("STEP 4: Monitoring Service Startup")
    print("="*80)
    
    print(f"⏳ Monitoring for up to {duration_seconds} seconds...")
    
    start_time = time.time()
    check_interval = 15
    
    while time.time() - start_time < duration_seconds:
        try:
            # Check service status
            response = ecs_client.describe_services(
                cluster=CLUSTER_NAME,
                services=[NEW_SERVICE_NAME]
            )
            
            service = response['services'][0]
            running_count = service['runningCount']
            desired_count = service['desiredCount']
            
            print(f"\n   Service Status:")
            print(f"   Running: {running_count}/{desired_count}")
            
            # Check target health
            response = elbv2_client.describe_target_health(
                TargetGroupArn=NLB_TARGET_GROUP_ARN
            )
            
            targets = response['TargetHealthDescriptions']
            
            if targets:
                print(f"   Target Health:")
                for target in targets:
                    target_id = target['Target']['Id']
                    health_state = target['TargetHealth']['State']
                    reason = target['TargetHealth'].get('Reason', 'N/A')
                    
                    print(f"   - {target_id}: {health_state} ({reason})")
                    
                    if health_state == 'healthy':
                        print(f"\n✅ Service is HEALTHY and RUNNING!")
                        return True
            else:
                print(f"   No targets registered yet")
            
            time.sleep(check_interval)
            
        except Exception as e:
            print(f"   ⚠️  Error checking status: {str(e)}")
            time.sleep(check_interval)
    
    print(f"\n⚠️  Timeout: Service did not become healthy within {duration_seconds} seconds")
    return False


def test_nlb_connectivity() -> bool:
    """Test NLB connectivity."""
    print("\n" + "="*80)
    print("STEP 5: Testing NLB Connectivity")
    print("="*80)
    
    nlb_dns = "multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com"
    
    import subprocess
    
    print(f"🔍 Testing: http://{nlb_dns}/api/health/simple")
    
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 
             f'http://{nlb_dns}/api/health/simple'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        status_code = result.stdout.strip()
        
        if status_code == '200':
            print(f"✅ Connectivity Test PASSED! (Status: {status_code})")
            return True
        else:
            print(f"⚠️  Connectivity Test returned: {status_code}")
            return False
            
    except Exception as e:
        print(f"⚠️  Connectivity Test failed: {str(e)}")
        return False


def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("SWITCH ECS SERVICE TO NLB")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'success': False,
        'steps': {}
    }
    
    try:
        # Get current task definition
        task_def_arn = get_current_task_definition()
        results['task_definition'] = task_def_arn
        
        # Step 1: Scale down
        scale_ok = scale_down_service()
        results['steps']['scale_down'] = scale_ok
        
        if not scale_ok:
            print("\n⚠️  Warning: Service did not scale down cleanly")
        
        # Step 2: Delete old service
        delete_ok = delete_old_service()
        results['steps']['delete_service'] = delete_ok
        
        if not delete_ok:
            raise Exception("Failed to delete old service")
        
        # Step 3: Create new service
        service_result = create_new_service_with_nlb(task_def_arn)
        results['steps']['create_service'] = service_result
        
        # Step 4: Monitor startup
        startup_ok = monitor_service_startup()
        results['steps']['startup'] = startup_ok
        
        # Step 5: Test connectivity
        connectivity_ok = test_nlb_connectivity()
        results['steps']['connectivity'] = connectivity_ok
        
        # Overall success
        results['success'] = startup_ok and connectivity_ok
        
        # Save results
        timestamp = int(time.time())
        filename = f"nlb-service-switch-{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Results saved to: {filename}")
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        
        if results['success']:
            print("✅ Service Switch to NLB SUCCESSFUL!")
            print(f"\n📋 Next Steps:")
            print(f"   1. Update CloudFront origin to NLB DNS")
            print(f"   2. Test HTTPS URL")
            print(f"   3. Monitor for stability")
            print(f"   4. Clean up old ALB resources")
        else:
            print("⚠️  Service Switch completed with warnings")
            if not startup_ok:
                print(f"   - Service did not start successfully")
            if not connectivity_ok:
                print(f"   - Connectivity test failed")
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        results['error'] = str(e)
        
        timestamp = int(time.time())
        filename = f"nlb-service-switch-error-{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 Error results saved to: {filename}")
        
        raise


if __name__ == '__main__':
    main()
