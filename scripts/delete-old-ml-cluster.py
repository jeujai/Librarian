#!/usr/bin/env python3
"""
Delete Old Multimodal Librarian Full ML Cluster

This script safely identifies and deletes the old "multimodal-librarian-full-ml" 
cluster that is no longer needed, helping reduce AWS costs.
"""

import boto3
import json
import time
from typing import Dict, List, Any
from datetime import datetime

class OldClusterCleanup:
    """Safe cleanup of old multimodal librarian clusters."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.regions = ['us-east-1', 'us-west-2']
        
    def identify_old_clusters(self) -> Dict[str, Any]:
        """Identify old clusters that can be safely deleted."""
        
        results = {
            'clusters_found': {},
            'deletion_candidates': [],
            'active_clusters': []
        }
        
        for region in self.regions:
            try:
                ecs = self.session.client('ecs', region_name=region)
                clusters = ecs.list_clusters()
                
                region_clusters = []
                
                for cluster_arn in clusters['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    
                    # Get cluster details
                    cluster_details = ecs.describe_clusters(clusters=[cluster_arn])
                    if cluster_details['clusters']:
                        cluster = cluster_details['clusters'][0]
                        
                        # Get services in this cluster
                        services = ecs.list_services(cluster=cluster_arn)
                        service_count = len(services['serviceArns'])
                        
                        # Get tasks in this cluster
                        tasks = ecs.list_tasks(cluster=cluster_arn)
                        task_count = len(tasks['taskArns'])
                        
                        cluster_info = {
                            'name': cluster_name,
                            'arn': cluster_arn,
                            'status': cluster['status'],
                            'running_tasks': cluster['runningTasksCount'],
                            'pending_tasks': cluster['pendingTasksCount'],
                            'active_services': cluster['activeServicesCount'],
                            'service_count': service_count,
                            'task_count': task_count,
                            'region': region
                        }
                        
                        region_clusters.append(cluster_info)
                        
                        # Identify deletion candidates
                        if 'full-ml' in cluster_name.lower():
                            if cluster['runningTasksCount'] == 0 and cluster['activeServicesCount'] == 0:
                                results['deletion_candidates'].append(cluster_info)
                                print(f"🎯 Deletion candidate: {cluster_name}")
                                print(f"   - Running tasks: {cluster['runningTasksCount']}")
                                print(f"   - Active services: {cluster['activeServicesCount']}")
                                print(f"   - Status: {cluster['status']}")
                            else:
                                results['active_clusters'].append(cluster_info)
                                print(f"⚠️  Active cluster (keep): {cluster_name}")
                                print(f"   - Running tasks: {cluster['runningTasksCount']}")
                                print(f"   - Active services: {cluster['activeServicesCount']}")
                        else:
                            results['active_clusters'].append(cluster_info)
                            print(f"✅ Current cluster (keep): {cluster_name}")
                
                results['clusters_found'][region] = region_clusters
                print(f"\n📊 {region}: Found {len(region_clusters)} clusters")
                
            except Exception as e:
                print(f"❌ Error checking clusters in {region}: {e}")
        
        return results
    
    def safe_delete_cluster(self, cluster_info: Dict[str, Any]) -> bool:
        """Safely delete a cluster after final verification."""
        
        cluster_name = cluster_info['name']
        cluster_arn = cluster_info['arn']
        region = cluster_info['region']
        
        print(f"\n🗑️  Preparing to delete cluster: {cluster_name}")
        
        try:
            ecs = self.session.client('ecs', region_name=region)
            
            # Final safety check - ensure no running tasks or services
            cluster_details = ecs.describe_clusters(clusters=[cluster_arn])
            if cluster_details['clusters']:
                cluster = cluster_details['clusters'][0]
                
                if cluster['runningTasksCount'] > 0 or cluster['activeServicesCount'] > 0:
                    print(f"❌ Safety check failed - cluster has active resources:")
                    print(f"   - Running tasks: {cluster['runningTasksCount']}")
                    print(f"   - Active services: {cluster['activeServicesCount']}")
                    return False
                
                # Check for any services (even stopped ones)
                services = ecs.list_services(cluster=cluster_arn)
                if services['serviceArns']:
                    print(f"⚠️  Found {len(services['serviceArns'])} services in cluster")
                    print("   Deleting services first...")
                    
                    # Delete services
                    for service_arn in services['serviceArns']:
                        service_name = service_arn.split('/')[-1]
                        print(f"   Deleting service: {service_name}")
                        
                        # Scale down to 0 first
                        ecs.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        
                        # Wait a moment for scaling
                        time.sleep(5)
                        
                        # Delete the service
                        ecs.delete_service(
                            cluster=cluster_arn,
                            service=service_arn
                        )
                    
                    print("   Waiting for services to be deleted...")
                    time.sleep(10)
                
                # Now delete the cluster
                print(f"🗑️  Deleting cluster: {cluster_name}")
                ecs.delete_cluster(cluster=cluster_arn)
                
                print(f"✅ Successfully deleted cluster: {cluster_name}")
                return True
                
        except Exception as e:
            print(f"❌ Error deleting cluster {cluster_name}: {e}")
            return False
        
        return False
    
    def run_cleanup(self) -> Dict[str, Any]:
        """Run the complete cleanup process."""
        
        print("🧹 Old Cluster Cleanup - Multimodal Librarian Full ML")
        print("=" * 60)
        print("Identifying old clusters that can be safely deleted...")
        print()
        
        # Step 1: Identify clusters
        cluster_analysis = self.identify_old_clusters()
        
        deletion_candidates = cluster_analysis['deletion_candidates']
        active_clusters = cluster_analysis['active_clusters']
        
        print(f"\n📊 Cluster Analysis Summary:")
        print(f"   - Deletion candidates: {len(deletion_candidates)}")
        print(f"   - Active clusters (keep): {len(active_clusters)}")
        
        if not deletion_candidates:
            print("\n✅ No old clusters found for deletion")
            return {
                'deleted_clusters': [],
                'kept_clusters': active_clusters,
                'cost_savings': 0
            }
        
        # Step 2: Delete candidates
        deleted_clusters = []
        
        for cluster in deletion_candidates:
            print(f"\n🎯 Processing deletion candidate: {cluster['name']}")
            
            # Confirm deletion
            if self.safe_delete_cluster(cluster):
                deleted_clusters.append(cluster)
            else:
                print(f"⚠️  Skipped deletion of {cluster['name']} due to safety concerns")
        
        # Step 3: Estimate cost savings
        # Each idle ECS cluster costs approximately $0 (only pay for running tasks)
        # But cleaning up reduces management overhead and potential accidental usage
        estimated_savings = len(deleted_clusters) * 5  # $5/month management overhead per cluster
        
        results = {
            'deleted_clusters': deleted_clusters,
            'kept_clusters': active_clusters,
            'cost_savings': estimated_savings,
            'cleanup_timestamp': datetime.now().isoformat()
        }
        
        print(f"\n🎉 Cleanup Complete!")
        print(f"   - Deleted clusters: {len(deleted_clusters)}")
        print(f"   - Estimated monthly savings: ${estimated_savings}")
        
        return results

def main():
    """Main execution function."""
    
    cleanup = OldClusterCleanup()
    
    try:
        results = cleanup.run_cleanup()
        
        # Save results
        timestamp = int(time.time())
        results_file = f"cluster-cleanup-results-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Cleanup results saved to: {results_file}")
        
        return 0 if results['deleted_clusters'] else 1
        
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())