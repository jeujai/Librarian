#!/usr/bin/env python3
"""
Immediate AWS Cost Reduction Script
Stops high-cost services that can be restarted if needed.
"""

import boto3
import json
import time
from datetime import datetime

def immediate_cost_reduction():
    """Stop high-cost services immediately (reversible actions)."""
    
    print("🚨 IMMEDIATE AWS COST REDUCTION")
    print("=" * 50)
    print("Stopping high-cost services (can be restarted if needed)")
    print()
    
    session = boto3.Session()
    results = {
        'timestamp': datetime.now().isoformat(),
        'actions_taken': [],
        'estimated_monthly_savings': 0,
        'errors': []
    }
    
    try:
        # 1. Stop Neptune Cluster (biggest cost)
        print("1. 🎯 Stopping Neptune Cluster ($115/month)")
        neptune = session.client('neptune', region_name='us-east-1')
        
        try:
            response = neptune.stop_db_cluster(
                DBClusterIdentifier='multimodal-lib-prod-neptune'
            )
            print("   ✅ Neptune cluster stop initiated")
            results['actions_taken'].append({
                'service': 'Neptune',
                'action': 'stop_cluster',
                'resource': 'multimodal-lib-prod-neptune',
                'monthly_savings': 115,
                'status': 'success'
            })
            results['estimated_monthly_savings'] += 115
        except Exception as e:
            print(f"   ❌ Error stopping Neptune: {e}")
            results['errors'].append(f"Neptune stop failed: {e}")
        
        # 2. Stop RDS instances
        print("\n2. 🗄️ Stopping RDS Instances ($15-20/month)")
        rds = session.client('rds', region_name='us-east-1')
        
        rds_instances = [
            'ml-librarian-postgres-prod',
            'multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro'
        ]
        
        for db_id in rds_instances:
            try:
                response = rds.stop_db_instance(DBInstanceIdentifier=db_id)
                print(f"   ✅ Stopped RDS instance: {db_id}")
                results['actions_taken'].append({
                    'service': 'RDS',
                    'action': 'stop_instance',
                    'resource': db_id,
                    'monthly_savings': 10,
                    'status': 'success'
                })
                results['estimated_monthly_savings'] += 10
            except Exception as e:
                print(f"   ❌ Error stopping {db_id}: {e}")
                results['errors'].append(f"RDS {db_id} stop failed: {e}")
        
        # 3. Scale down ECS services to 0
        print("\n3. 📦 Scaling down ECS Services ($100/month)")
        ecs = session.client('ecs', region_name='us-east-1')
        
        try:
            # List all clusters
            clusters = ecs.list_clusters()
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                print(f"   Checking cluster: {cluster_name}")
                
                # List services in cluster
                services = ecs.list_services(cluster=cluster_arn)
                
                for service_arn in services['serviceArns']:
                    service_name = service_arn.split('/')[-1]
                    
                    try:
                        # Scale service to 0
                        response = ecs.update_service(
                            cluster=cluster_arn,
                            service=service_arn,
                            desiredCount=0
                        )
                        print(f"   ✅ Scaled {service_name} to 0 tasks")
                        results['actions_taken'].append({
                            'service': 'ECS',
                            'action': 'scale_to_zero',
                            'resource': f"{cluster_name}/{service_name}",
                            'monthly_savings': 20,
                            'status': 'success'
                        })
                        results['estimated_monthly_savings'] += 20
                    except Exception as e:
                        print(f"   ❌ Error scaling {service_name}: {e}")
                        results['errors'].append(f"ECS {service_name} scale failed: {e}")
            
            if not clusters['clusterArns']:
                print("   ℹ️ No ECS clusters found")
                
        except Exception as e:
            print(f"   ❌ Error with ECS operations: {e}")
            results['errors'].append(f"ECS operations failed: {e}")
        
        # 4. Stop EC2 instances
        print("\n4. ��️ Stopping EC2 Instances")
        ec2 = session.client('ec2', region_name='us-east-1')
        
        try:
            # Stop the Neo4j instance if it's running
            response = ec2.describe_instances(InstanceIds=['i-0255d25fd1950ed2d'])
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] == 'running':
                        ec2.stop_instances(InstanceIds=['i-0255d25fd1950ed2d'])
                        print("   ✅ Stopped Neo4j instance (i-0255d25fd1950ed2d)")
                        results['actions_taken'].append({
                            'service': 'EC2',
                            'action': 'stop_instance',
                            'resource': 'i-0255d25fd1950ed2d',
                            'monthly_savings': 25,
                            'status': 'success'
                        })
                        results['estimated_monthly_savings'] += 25
                    else:
                        print(f"   ℹ️ Instance already stopped: {instance['State']['Name']}")
                        
        except Exception as e:
            print(f"   ❌ Error stopping EC2: {e}")
            results['errors'].append(f"EC2 stop failed: {e}")
        
        # Summary
        print(f"\n📊 IMMEDIATE SAVINGS SUMMARY")
        print("=" * 40)
        print(f"💰 Estimated Monthly Savings: ${results['estimated_monthly_savings']}")
        print(f"📅 Actions Taken: {len(results['actions_taken'])}")
        print(f"❌ Errors: {len(results['errors'])}")
        
        if results['actions_taken']:
            print(f"\n✅ Successfully stopped services:")
            for action in results['actions_taken']:
                print(f"   - {action['service']}: {action['resource']} (${action['monthly_savings']}/month)")
        
        if results['errors']:
            print(f"\n❌ Errors encountered:")
            for error in results['errors']:
                print(f"   - {error}")
        
        print(f"\n⚠️ IMPORTANT NOTES:")
        print("- All stopped services can be restarted if needed")
        print("- Neptune: Can be restarted within 7 days")
        print("- RDS: Can be restarted within 7 days")
        print("- ECS: Can be scaled back up immediately")
        print("- EC2: Can be restarted immediately")
        
        # Save results
        timestamp = int(time.time())
        results_file = f"immediate-cost-reduction-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Results saved to: {results_file}")
        
        return results
        
    except Exception as e:
        print(f"❌ Script failed: {e}")
        return None

if __name__ == "__main__":
    immediate_cost_reduction()
