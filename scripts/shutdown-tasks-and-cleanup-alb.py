#!/usr/bin/env python3
"""
Script to:
1. Shutdown all ECS tasks (set desired count to 0)
2. Remove the unused multimodal-librarian-full-ml ALB and associated resources
"""

import boto3
import json
import time
from datetime import datetime

def get_all_ecs_services():
    """Get all ECS services across all clusters."""
    ecs = boto3.client('ecs')
    
    print("🔍 Finding all ECS clusters and services...")
    
    # Get all clusters
    clusters_response = ecs.list_clusters()
    clusters = clusters_response.get('clusterArns', [])
    
    all_services = []
    
    for cluster_arn in clusters:
        cluster_name = cluster_arn.split('/')[-1]
        print(f"  📊 Checking cluster: {cluster_name}")
        
        try:
            services_response = ecs.list_services(cluster=cluster_arn)
            if services_response['serviceArns']:
                # Get detailed service info
                services_detail = ecs.describe_services(
                    cluster=cluster_arn,
                    services=services_response['serviceArns']
                )
                
                for service in services_detail['services']:
                    all_services.append({
                        'cluster_name': cluster_name,
                        'cluster_arn': cluster_arn,
                        'service_name': service['serviceName'],
                        'service_arn': service['serviceArn'],
                        'desired_count': service['desiredCount'],
                        'running_count': service['runningCount'],
                        'status': service['status']
                    })
                    print(f"    - {service['serviceName']}: {service['runningCount']}/{service['desiredCount']} tasks")
        except Exception as e:
            print(f"    ⚠️  Error checking cluster {cluster_name}: {e}")
    
    return all_services

def shutdown_all_tasks():
    """Set desired count to 0 for all ECS services."""
    ecs = boto3.client('ecs')
    
    print("\n🛑 Shutting down all ECS tasks...")
    print("=" * 60)
    
    services = get_all_ecs_services()
    
    if not services:
        print("  ✅ No ECS services found")
        return []
    
    shutdown_results = []
    
    for service in services:
        if service['desired_count'] > 0:
            print(f"\n📊 Shutting down: {service['service_name']} in {service['cluster_name']}")
            print(f"  Current: {service['running_count']}/{service['desired_count']} tasks")
            
            try:
                response = ecs.update_service(
                    cluster=service['cluster_arn'],
                    service=service['service_arn'],
                    desiredCount=0
                )
                
                shutdown_results.append({
                    'cluster_name': service['cluster_name'],
                    'service_name': service['service_name'],
                    'previous_count': service['desired_count'],
                    'status': 'SUCCESS'
                })
                
                print(f"  ✅ Successfully set desired count to 0")
                
            except Exception as e:
                print(f"  ❌ Error shutting down service: {e}")
                shutdown_results.append({
                    'cluster_name': service['cluster_name'],
                    'service_name': service['service_name'],
                    'previous_count': service['desired_count'],
                    'status': 'ERROR',
                    'error': str(e)
                })
        else:
            print(f"  ✅ {service['service_name']} already has 0 desired count")
    
    return shutdown_results

def wait_for_tasks_to_stop():
    """Wait for all tasks to actually stop."""
    print("\n⏳ Waiting for tasks to stop...")
    
    max_wait_time = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        services = get_all_ecs_services()
        running_tasks = sum(service['running_count'] for service in services)
        
        if running_tasks == 0:
            print("  ✅ All tasks have stopped")
            return True
        
        print(f"  ⏳ Still waiting... {running_tasks} tasks running")
        time.sleep(10)
    
    print("  ⚠️  Timeout waiting for tasks to stop, proceeding anyway")
    return False

def remove_multimodal_librarian_full_ml():
    """Remove the unused multimodal-librarian-full-ml ALB and associated resources."""
    elbv2 = boto3.client('elbv2')
    
    print("\n🗑️  Removing multimodal-librarian-full-ml ALB...")
    print("=" * 60)
    
    alb_name = "multimodal-librarian-full-ml"
    
    try:
        # Get ALB details
        response = elbv2.describe_load_balancers(Names=[alb_name])
        if not response['LoadBalancers']:
            print(f"  ✅ ALB {alb_name} not found (already deleted?)")
            return {'status': 'NOT_FOUND'}
        
        alb = response['LoadBalancers'][0]
        alb_arn = alb['LoadBalancerArn']
        
        print(f"  📊 Found ALB: {alb['DNSName']}")
        print(f"  📊 State: {alb['State']['Code']}")
        print(f"  📊 VPC: {alb['VpcId']}")
        
        # Get target groups
        target_groups_response = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
        target_groups = target_groups_response['TargetGroups']
        
        print(f"  📊 Target Groups: {len(target_groups)}")
        
        # Verify no targets are registered
        for tg in target_groups:
            health_response = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
            targets = health_response['TargetHealthDescriptions']
            
            if targets:
                print(f"  ⚠️  Target group {tg['TargetGroupName']} has {len(targets)} targets!")
                print("  ❌ Cannot delete ALB with registered targets")
                return {'status': 'ERROR', 'reason': 'Targets still registered'}
            else:
                print(f"  ✅ Target group {tg['TargetGroupName']} has no targets")
        
        # Delete the ALB
        print(f"\n🗑️  Deleting ALB: {alb_name}")
        elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
        print(f"  ✅ ALB deletion initiated")
        
        # Wait for ALB to be deleted before deleting target groups
        print("  ⏳ Waiting for ALB to be deleted...")
        waiter = elbv2.get_waiter('load_balancers_deleted')
        waiter.wait(LoadBalancerArns=[alb_arn], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        print("  ✅ ALB successfully deleted")
        
        # Delete target groups
        for tg in target_groups:
            print(f"  🗑️  Deleting target group: {tg['TargetGroupName']}")
            try:
                elbv2.delete_target_group(TargetGroupArn=tg['TargetGroupArn'])
                print(f"    ✅ Target group deleted")
            except Exception as e:
                print(f"    ⚠️  Error deleting target group: {e}")
        
        return {
            'status': 'SUCCESS',
            'alb_name': alb_name,
            'alb_arn': alb_arn,
            'target_groups_deleted': len(target_groups)
        }
        
    except Exception as e:
        print(f"  ❌ Error removing ALB: {e}")
        return {'status': 'ERROR', 'error': str(e)}

def main():
    """Main execution function."""
    print("🚀 ECS Task Shutdown and ALB Cleanup")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    results = {
        'execution_time': datetime.now().isoformat(),
        'task_shutdown': [],
        'alb_cleanup': {}
    }
    
    try:
        # Step 1: Shutdown all ECS tasks
        shutdown_results = shutdown_all_tasks()
        results['task_shutdown'] = shutdown_results
        
        # Step 2: Wait for tasks to stop
        wait_for_tasks_to_stop()
        
        # Step 3: Remove the unused ALB
        alb_cleanup_result = remove_multimodal_librarian_full_ml()
        results['alb_cleanup'] = alb_cleanup_result
        
        # Summary
        print(f"\n📋 Summary")
        print("=" * 60)
        
        successful_shutdowns = len([r for r in shutdown_results if r['status'] == 'SUCCESS'])
        print(f"Services shutdown: {successful_shutdowns}/{len(shutdown_results)}")
        
        if alb_cleanup_result['status'] == 'SUCCESS':
            print(f"ALB cleanup: ✅ SUCCESS")
            print(f"Monthly savings: ~$16-22")
        elif alb_cleanup_result['status'] == 'NOT_FOUND':
            print(f"ALB cleanup: ✅ ALB already removed")
        else:
            print(f"ALB cleanup: ❌ {alb_cleanup_result['status']}")
        
        # Save results
        with open(f'shutdown-and-cleanup-results-{int(time.time())}.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: shutdown-and-cleanup-results-{int(time.time())}.json")
        
        return 0
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        results['error'] = str(e)
        
        with open(f'shutdown-and-cleanup-error-{int(time.time())}.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return 1

if __name__ == "__main__":
    exit(main())