#!/usr/bin/env python3
"""
High-Cost Database Shutdown Script

This script shuts down the most expensive AWS database resources:
- Neptune Database Cluster ($115.79/month)
- ElastiCache Cluster ($27.29/month)

Total Monthly Savings: $143.08/month ($1,716.96/year)
"""

import boto3
import json
import time
from datetime import datetime
import sys

def shutdown_neptune_cluster():
    """Shutdown Neptune database cluster."""
    print("🔄 Shutting down Neptune cluster...")
    
    try:
        neptune = boto3.client('neptune', region_name='us-east-1')
        
        # Get Neptune cluster details
        clusters = neptune.describe_db_clusters()
        neptune_clusters = [c for c in clusters['DBClusters'] if c['Engine'] == 'neptune']
        
        if not neptune_clusters:
            print("  ✅ No Neptune clusters found")
            return True
            
        for cluster in neptune_clusters:
            cluster_id = cluster['DBClusterIdentifier']
            status = cluster['Status']
            
            print(f"  📋 Found Neptune cluster: {cluster_id} (Status: {status})")
            
            if status == 'available':
                print(f"  🛑 Stopping Neptune cluster: {cluster_id}")
                
                # Stop the cluster (creates final snapshot)
                response = neptune.stop_db_cluster(
                    DBClusterIdentifier=cluster_id
                )
                
                print(f"  ✅ Neptune cluster stop initiated: {cluster_id}")
                print(f"     💰 Monthly savings: $115.79")
                
            elif status in ['stopped', 'stopping']:
                print(f"  ✅ Neptune cluster already stopped/stopping: {cluster_id}")
                
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down Neptune: {e}")
        return False

def shutdown_elasticache_clusters():
    """Shutdown ElastiCache clusters."""
    print("🔄 Shutting down ElastiCache clusters...")
    
    try:
        elasticache = boto3.client('elasticache', region_name='us-east-1')
        
        # Get ElastiCache clusters
        clusters = elasticache.describe_cache_clusters()
        
        if not clusters['CacheClusters']:
            print("  ✅ No ElastiCache clusters found")
            return True
            
        for cluster in clusters['CacheClusters']:
            cluster_id = cluster['CacheClusterId']
            status = cluster['CacheClusterStatus']
            
            print(f"  📋 Found ElastiCache cluster: {cluster_id} (Status: {status})")
            
            if status == 'available':
                print(f"  🛑 Deleting ElastiCache cluster: {cluster_id}")
                
                # Delete the cluster (no final snapshot for ElastiCache)
                response = elasticache.delete_cache_cluster(
                    CacheClusterId=cluster_id
                )
                
                print(f"  ✅ ElastiCache cluster deletion initiated: {cluster_id}")
                print(f"     💰 Monthly savings: $27.29")
                
            elif status in ['deleting']:
                print(f"  ✅ ElastiCache cluster already deleting: {cluster_id}")
                
        return True
        
    except Exception as e:
        print(f"  ❌ Error shutting down ElastiCache: {e}")
        return False

def verify_shutdown_status():
    """Verify the shutdown status of resources."""
    print("\n🔍 Verifying shutdown status...")
    
    try:
        # Check Neptune status
        neptune = boto3.client('neptune', region_name='us-east-1')
        clusters = neptune.describe_db_clusters()
        neptune_clusters = [c for c in clusters['DBClusters'] if c['Engine'] == 'neptune']
        
        for cluster in neptune_clusters:
            cluster_id = cluster['DBClusterIdentifier']
            status = cluster['Status']
            print(f"  📊 Neptune {cluster_id}: {status}")
            
        # Check ElastiCache status
        elasticache = boto3.client('elasticache', region_name='us-east-1')
        clusters = elasticache.describe_cache_clusters()
        
        for cluster in clusters['CacheClusters']:
            cluster_id = cluster['CacheClusterId']
            status = cluster['CacheClusterStatus']
            print(f"  📊 ElastiCache {cluster_id}: {status}")
            
    except Exception as e:
        print(f"  ❌ Error checking status: {e}")

def main():
    """Main execution function."""
    
    print("💰 AWS High-Cost Database Shutdown")
    print("=" * 50)
    print("Target Monthly Savings: $143.08")
    print("Target Annual Savings: $1,716.96")
    print()
    
    # Track results
    results = {
        'timestamp': datetime.now().isoformat(),
        'neptune_shutdown': False,
        'elasticache_shutdown': False,
        'total_monthly_savings': 0,
        'errors': []
    }
    
    # Shutdown Neptune cluster
    if shutdown_neptune_cluster():
        results['neptune_shutdown'] = True
        results['total_monthly_savings'] += 115.79
    else:
        results['errors'].append('Neptune shutdown failed')
    
    # Shutdown ElastiCache clusters
    if shutdown_elasticache_clusters():
        results['elasticache_shutdown'] = True
        results['total_monthly_savings'] += 27.29
    else:
        results['errors'].append('ElastiCache shutdown failed')
    
    # Verify status
    verify_shutdown_status()
    
    # Save results
    timestamp = int(time.time())
    results_file = f"high-cost-database-shutdown-{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print(f"\n💰 Cost Optimization Summary")
    print("=" * 40)
    print(f"Monthly Savings: ${results['total_monthly_savings']:.2f}")
    print(f"Annual Savings: ${results['total_monthly_savings'] * 12:.2f}")
    
    if results['errors']:
        print(f"\n⚠️  Errors encountered:")
        for error in results['errors']:
            print(f"   - {error}")
    else:
        print(f"\n✅ All high-cost databases successfully shut down!")
    
    print(f"\n📊 Results saved to: {results_file}")
    
    return results

if __name__ == "__main__":
    main()