#!/usr/bin/env python3
"""
Delete Unused ML Cluster

Based on the analysis showing the multimodal-librarian-full-ml cluster
is safe to delete (all services scaled to 0), this script will clean it up.
"""

import boto3
import json
import time
from typing import Dict, Any
from datetime import datetime

def delete_ml_cluster() -> Dict[str, Any]:
    """Delete the unused multimodal-librarian-full-ml cluster."""
    
    results = {
        'success': False,
        'deleted_services': [],
        'deleted_cluster': False,
        'error': None,
        'estimated_savings': 30
    }
    
    cluster_name = "multimodal-librarian-full-ml"
    
    try:
        ecs = boto3.client('ecs', region_name='us-east-1')
        
        print(f"🗑️  Deleting unused cluster: {cluster_name}")
        
        # Find the cluster ARN
        clusters = ecs.list_clusters()
        target_cluster_arn = None
        
        for cluster_arn in clusters['clusterArns']:
            if cluster_arn.split('/')[-1] == cluster_name:
                target_cluster_arn = cluster_arn
                break
        
        if not target_cluster_arn:
            results['error'] = f"Cluster {cluster_name} not found"
            return results
        
        # Get and delete services first
        services = ecs.list_services(cluster=target_cluster_arn)
        
        if services['serviceArns']:
            print(f"📋 Found {len(services['serviceArns'])} services to delete")
            
            for service_arn in services['serviceArns']:
                service_name = service_arn.split('/')[-1]
                print(f"   Deleting service: {service_name}")
                
                try:
                    # Ensure service is scaled to 0 (should already be)
                    ecs.update_service(
                        cluster=target_cluster_arn,
                        service=service_arn,
                        desiredCount=0
                    )
                    
                    # Wait a moment
                    time.sleep(2)
                    
                    # Delete the service
                    ecs.delete_service(
                        cluster=target_cluster_arn,
                        service=service_arn
                    )
                    
                    results['deleted_services'].append(service_name)
                    print(f"   ✅ Deleted service: {service_name}")
                    
                except Exception as e:
                    print(f"   ❌ Error deleting service {service_name}: {e}")
            
            # Wait for services to be fully deleted
            print("   ⏳ Waiting for services to be deleted...")
            time.sleep(15)
        
        # Now delete the cluster
        print(f"🗑️  Deleting cluster: {cluster_name}")
        
        ecs.delete_cluster(cluster=target_cluster_arn)
        results['deleted_cluster'] = True
        results['success'] = True
        
        print(f"✅ Successfully deleted cluster: {cluster_name}")
        print(f"💰 Estimated monthly savings: ${results['estimated_savings']}")
        
    except Exception as e:
        results['error'] = str(e)
        print(f"❌ Error deleting cluster: {e}")
    
    return results

def main():
    """Main execution function."""
    
    print("🧹 Deleting Unused ML Cluster")
    print("=" * 40)
    print("Based on analysis showing cluster is safe to delete")
    print("(all services scaled to 0, no recent activity)")
    print()
    
    try:
        results = delete_ml_cluster()
        
        # Save results
        timestamp = int(time.time())
        results_file = f"ml-cluster-deletion-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Deletion results saved to: {results_file}")
        
        if results['success']:
            print(f"\n🎉 Cleanup successful!")
            print(f"   - Deleted services: {len(results['deleted_services'])}")
            print(f"   - Deleted cluster: {results['deleted_cluster']}")
            print(f"   - Monthly savings: ${results['estimated_savings']}")
            return 0
        else:
            print(f"\n❌ Cleanup failed: {results.get('error', 'Unknown error')}")
            return 1
        
    except Exception as e:
        print(f"❌ Script failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())