#!/usr/bin/env python3
"""
Scale ECS service to 0 tasks in multimodal-lib-prod-cluster.
This stops all running tasks without deleting the service.
"""

import boto3
import sys
import time
from datetime import datetime

def scale_service_to_zero():
    """Scale the ECS service to 0 desired tasks."""
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    cluster_name = 'multimodal-lib-prod-cluster'
    
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"=" * 80)
    print(f"Scaling service in cluster: {cluster_name}")
    print(f"=" * 80)
    
    try:
        # List services in the cluster
        print("\n1. Listing services in cluster...")
        services_response = ecs.list_services(cluster=cluster_name)
        
        if not services_response['serviceArns']:
            print(f"❌ No services found in cluster {cluster_name}")
            return False
        
        service_arns = services_response['serviceArns']
        print(f"✓ Found {len(service_arns)} service(s)")
        
        # Get service details
        print("\n2. Getting service details...")
        services_detail = ecs.describe_services(
            cluster=cluster_name,
            services=service_arns
        )
        
        for service in services_detail['services']:
            service_name = service['serviceName']
            current_desired = service['desiredCount']
            current_running = service['runningCount']
            
            print(f"\nService: {service_name}")
            print(f"  Current desired count: {current_desired}")
            print(f"  Current running count: {current_running}")
            
            if current_desired == 0:
                print(f"  ℹ️  Service already scaled to 0")
                continue
            
            # Scale to 0
            print(f"\n3. Scaling {service_name} to 0 tasks...")
            update_response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                desiredCount=0
            )
            
            print(f"✓ Service update initiated")
            print(f"  New desired count: {update_response['service']['desiredCount']}")
            
            # Wait for tasks to stop
            print(f"\n4. Waiting for tasks to stop...")
            max_wait = 120  # 2 minutes
            wait_interval = 5
            elapsed = 0
            
            while elapsed < max_wait:
                service_status = ecs.describe_services(
                    cluster=cluster_name,
                    services=[service_name]
                )
                
                running_count = service_status['services'][0]['runningCount']
                
                if running_count == 0:
                    print(f"✓ All tasks stopped (0 running)")
                    break
                
                print(f"  Still running: {running_count} task(s)... waiting {wait_interval}s")
                time.sleep(wait_interval)
                elapsed += wait_interval
            
            if running_count > 0:
                print(f"⚠️  Warning: {running_count} task(s) still running after {max_wait}s")
                print(f"  Tasks may take additional time to fully stop")
            
            # Final status
            print(f"\n5. Final service status:")
            final_status = ecs.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            final_service = final_status['services'][0]
            print(f"  Service: {final_service['serviceName']}")
            print(f"  Status: {final_service['status']}")
            print(f"  Desired count: {final_service['desiredCount']}")
            print(f"  Running count: {final_service['runningCount']}")
            print(f"  Pending count: {final_service['pendingCount']}")
        
        print(f"\n{'=' * 80}")
        print(f"✓ Service scaled to 0 tasks successfully")
        print(f"{'=' * 80}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error scaling service: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = scale_service_to_zero()
    sys.exit(0 if success else 1)
