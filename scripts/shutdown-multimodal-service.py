#!/usr/bin/env python3
"""
Simple script to shutdown the multimodal-lib-prod-service by setting desired count to 0.
"""

import boto3
import json
import time
from datetime import datetime

def shutdown_multimodal_service():
    """Set desired count to 0 for multimodal-lib-prod-service."""
    ecs = boto3.client('ecs')
    
    print("🛑 Shutting down multimodal-lib-prod-service...")
    print("=" * 50)
    
    service_name = "multimodal-lib-prod-service"
    cluster_name = "multimodal-lib-prod-cluster"  # Assuming this is the cluster name
    
    try:
        # Get current service status
        print(f"📊 Checking current status of {service_name}...")
        
        response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not response['services']:
            print(f"  ❌ Service {service_name} not found in cluster {cluster_name}")
            return {'status': 'NOT_FOUND'}
        
        service = response['services'][0]
        current_desired = service['desiredCount']
        current_running = service['runningCount']
        
        print(f"  📊 Current status: {current_running}/{current_desired} tasks")
        
        if current_desired == 0:
            print(f"  ✅ Service already has 0 desired count")
            return {'status': 'ALREADY_SHUTDOWN', 'previous_count': current_desired}
        
        # Update service to desired count 0
        print(f"  🛑 Setting desired count to 0...")
        
        update_response = ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=0
        )
        
        print(f"  ✅ Successfully set desired count to 0")
        print(f"  ⏳ Tasks will stop shortly...")
        
        return {
            'status': 'SUCCESS',
            'previous_count': current_desired,
            'cluster': cluster_name,
            'service': service_name,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def main():
    """Main execution function."""
    print("🚀 Multimodal Service Shutdown")
    print("=" * 50)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    result = shutdown_multimodal_service()
    
    # Summary
    print(f"\n📋 Summary")
    print("=" * 50)
    
    if result['status'] == 'SUCCESS':
        print(f"✅ Service shutdown initiated successfully")
        print(f"Previous task count: {result['previous_count']}")
        print(f"New task count: 0")
    elif result['status'] == 'ALREADY_SHUTDOWN':
        print(f"✅ Service was already shutdown")
    elif result['status'] == 'NOT_FOUND':
        print(f"❌ Service not found")
    else:
        print(f"❌ Shutdown failed: {result.get('error', 'Unknown error')}")
    
    # Save results
    timestamp = int(time.time())
    filename = f'multimodal-service-shutdown-{timestamp}.json'
    
    with open(filename, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n💾 Results saved to: {filename}")
    
    return 0 if result['status'] in ['SUCCESS', 'ALREADY_SHUTDOWN'] else 1

if __name__ == "__main__":
    exit(main())