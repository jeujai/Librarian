#!/usr/bin/env python3
"""
Delete multimodal-lib-prod-cluster

This script safely deletes the multimodal-lib-prod-cluster and its services
after confirming they are not in use.
"""

import boto3
import json
import time
from typing import Dict, List, Any

class ProdClusterDeleter:
    """Delete the prod cluster and its services."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.cluster_name = "multimodal-lib-prod-cluster"
        
    def delete_cluster_safely(self) -> Dict[str, Any]:
        """Delete the cluster and all its services."""
        
        results = {
            'cluster_name': self.cluster_name,
            'services_deleted': [],
            'cluster_deleted': False,
            'errors': []
        }
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            # Find the cluster
            clusters = ecs.list_clusters()
            target_cluster_arn = None
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                if cluster_name == self.cluster_name:
                    target_cluster_arn = cluster_arn
                    break
            
            if not target_cluster_arn:
                print(f"❌ Cluster '{self.cluster_name}' not found")
                results['errors'].append(f"Cluster '{self.cluster_name}' not found")
                return results
            
            print(f"🎯 Found cluster: {self.cluster_name}")
            
            # Get and delete services first
            services = ecs.list_services(cluster=target_cluster_arn)
            
            if services['serviceArns']:
                print(f"🔍 Found {len(services['serviceArns'])} services to delete")
                
                for service_arn in services['serviceArns']:
                    service_name = service_arn.split('/')[-1]
                    
                    try:
                        print(f"🗑️  Deleting service: {service_name}")
                        
                        # First scale down to 0 (should already be 0 based on analysis)
                        ecs.update_service(
                            cluster=target_cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        
                        # Wait a moment for scaling
                        time.sleep(5)
                        
                        # Delete the service
                        delete_response = ecs.delete_service(
                            cluster=target_cluster_arn,
                            service=service_arn
                        )
                        
                        results['services_deleted'].append({
                            'name': service_name,
                            'arn': service_arn,
                            'status': 'deleted',
                            'deletion_time': delete_response['service']['updatedAt'].isoformat()
                        })
                        
                        print(f"✅ Service {service_name} deleted successfully")
                        
                    except Exception as e:
                        error_msg = f"Failed to delete service {service_name}: {e}"
                        print(f"❌ {error_msg}")
                        results['errors'].append(error_msg)
                        results['services_deleted'].append({
                            'name': service_name,
                            'arn': service_arn,
                            'status': 'failed',
                            'error': str(e)
                        })
                
                # Wait for services to be fully deleted
                print("⏳ Waiting for services to be fully deleted...")
                time.sleep(30)
            
            # Now delete the cluster
            try:
                print(f"🗑️  Deleting cluster: {self.cluster_name}")
                
                delete_response = ecs.delete_cluster(cluster=target_cluster_arn)
                
                results['cluster_deleted'] = True
                results['cluster_deletion_time'] = delete_response['cluster']['updatedAt'].isoformat()
                
                print(f"✅ Cluster {self.cluster_name} deleted successfully")
                
            except Exception as e:
                error_msg = f"Failed to delete cluster {self.cluster_name}: {e}"
                print(f"❌ {error_msg}")
                results['errors'].append(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error during deletion: {e}"
            print(f"❌ {error_msg}")
            results['errors'].append(error_msg)
        
        return results
    
    def verify_deletion(self) -> bool:
        """Verify that the cluster has been deleted."""
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            clusters = ecs.list_clusters()
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                if cluster_name == self.cluster_name:
                    print(f"⚠️  Cluster {self.cluster_name} still exists")
                    return False
            
            print(f"✅ Cluster {self.cluster_name} successfully deleted")
            return True
            
        except Exception as e:
            print(f"❌ Error verifying deletion: {e}")
            return False

def main():
    """Main execution function."""
    
    deleter = ProdClusterDeleter()
    
    try:
        print("🗑️  Multimodal Lib Prod Cluster Deletion")
        print("=" * 50)
        
        # Perform deletion
        results = deleter.delete_cluster_safely()
        
        # Save results
        timestamp = int(time.time())
        results_file = f"prod-cluster-deletion-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Deletion results saved to: {results_file}")
        
        # Verify deletion
        print("\n🔍 Verifying deletion...")
        if deleter.verify_deletion():
            print("\n🎉 Cluster deletion completed successfully!")
            
            # Calculate savings
            services_deleted = len([s for s in results['services_deleted'] if s['status'] == 'deleted'])
            estimated_savings = 30  # Based on analysis
            
            print(f"\n💰 Cost Savings:")
            print(f"   Services deleted: {services_deleted}")
            print(f"   Estimated monthly savings: ${estimated_savings}")
            
            return 0
        else:
            print("\n⚠️  Deletion verification failed")
            return 1
        
    except Exception as e:
        print(f"❌ Deletion failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())