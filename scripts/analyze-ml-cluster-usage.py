#!/usr/bin/env python3
"""
Analyze ML Cluster Usage

This script provides detailed analysis of what's running in the 
multimodal-librarian-full-ml cluster to determine if it's still needed.
"""

import boto3
import json
import time
from typing import Dict, List, Any
from datetime import datetime, timedelta

class MLClusterAnalyzer:
    """Analyze ML cluster usage and determine if it's still needed."""
    
    def __init__(self, cluster_name: str = "multimodal-librarian-full-ml"):
        self.session = boto3.Session()
        self.target_cluster = cluster_name
        
    def analyze_cluster_details(self) -> Dict[str, Any]:
        """Get detailed analysis of the ML cluster."""
        
        results = {
            'cluster_info': {},
            'services': [],
            'tasks': [],
            'recent_activity': {},
            'recommendation': 'unknown'
        }
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            # Find the cluster
            clusters = ecs.list_clusters()
            target_cluster_arn = None
            
            for cluster_arn in clusters['clusterArns']:
                cluster_name = cluster_arn.split('/')[-1]
                if cluster_name == self.target_cluster:
                    target_cluster_arn = cluster_arn
                    break
            
            if not target_cluster_arn:
                print(f"❌ Cluster '{self.target_cluster}' not found")
                return results
            
            # Get cluster details
            cluster_details = ecs.describe_clusters(clusters=[target_cluster_arn])
            if cluster_details['clusters']:
                cluster = cluster_details['clusters'][0]
                results['cluster_info'] = {
                    'name': cluster['clusterName'],
                    'status': cluster['status'],
                    'running_tasks': cluster['runningTasksCount'],
                    'pending_tasks': cluster['pendingTasksCount'],
                    'active_services': cluster['activeServicesCount'],
                    'registered_container_instances': cluster['registeredContainerInstancesCount']
                }
                
                print(f"🔍 Analyzing cluster: {cluster['clusterName']}")
                print(f"   Status: {cluster['status']}")
                print(f"   Running tasks: {cluster['runningTasksCount']}")
                print(f"   Active services: {cluster['activeServicesCount']}")
            
            # Get services
            services = ecs.list_services(cluster=target_cluster_arn)
            service_details = []
            
            if services['serviceArns']:
                service_descriptions = ecs.describe_services(
                    cluster=target_cluster_arn,
                    services=services['serviceArns']
                )
                
                for service in service_descriptions['services']:
                    service_info = {
                        'name': service['serviceName'],
                        'status': service['status'],
                        'task_definition': service['taskDefinition'],
                        'desired_count': service['desiredCount'],
                        'running_count': service['runningCount'],
                        'pending_count': service['pendingCount'],
                        'created_at': service['createdAt'].isoformat(),
                        'updated_at': service.get('updatedAt', service['createdAt']).isoformat()
                    }
                    
                    # Get task definition details
                    task_def_arn = service['taskDefinition']
                    task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)
                    
                    if 'taskDefinition' in task_def:
                        td = task_def['taskDefinition']
                        service_info['cpu'] = td.get('cpu', 'N/A')
                        service_info['memory'] = td.get('memory', 'N/A')
                        service_info['container_count'] = len(td.get('containerDefinitions', []))
                        
                        # Get container names
                        containers = [c['name'] for c in td.get('containerDefinitions', [])]
                        service_info['containers'] = containers
                    
                    service_details.append(service_info)
                    
                    print(f"\n📋 Service: {service['serviceName']}")
                    print(f"   Status: {service['status']}")
                    print(f"   Desired/Running: {service['desiredCount']}/{service['runningCount']}")
                    print(f"   Task Definition: {service['taskDefinition'].split('/')[-1]}")
                    print(f"   Containers: {service_info.get('containers', [])}")
                    print(f"   CPU/Memory: {service_info.get('cpu', 'N/A')}/{service_info.get('memory', 'N/A')}")
                    print(f"   Last Updated: {service_info['updated_at']}")
            
            results['services'] = service_details
            
            # Get running tasks
            tasks = ecs.list_tasks(cluster=target_cluster_arn)
            task_details = []
            
            if tasks['taskArns']:
                task_descriptions = ecs.describe_tasks(
                    cluster=target_cluster_arn,
                    tasks=tasks['taskArns']
                )
                
                for task in task_descriptions['tasks']:
                    task_info = {
                        'task_arn': task['taskArn'],
                        'task_definition': task['taskDefinitionArn'],
                        'last_status': task['lastStatus'],
                        'desired_status': task['desiredStatus'],
                        'created_at': task['createdAt'].isoformat(),
                        'started_at': task.get('startedAt', task['createdAt']).isoformat(),
                        'cpu_utilization': 'N/A',
                        'memory_utilization': 'N/A'
                    }
                    task_details.append(task_info)
                    
                    print(f"\n📦 Task: {task['taskArn'].split('/')[-1]}")
                    print(f"   Status: {task['lastStatus']}")
                    print(f"   Started: {task_info['started_at']}")
            
            results['tasks'] = task_details
            
            # Analyze recent activity using CloudWatch
            try:
                cloudwatch = self.session.client('cloudwatch', region_name='us-east-1')
                
                # Get CPU utilization for the past 7 days
                end_time = datetime.now()
                start_time = end_time - timedelta(days=7)
                
                cpu_metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/ECS',
                    MetricName='CPUUtilization',
                    Dimensions=[
                        {'Name': 'ClusterName', 'Value': self.target_cluster}
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour periods
                    Statistics=['Average', 'Maximum']
                )
                
                if cpu_metrics['Datapoints']:
                    avg_cpu = sum(dp['Average'] for dp in cpu_metrics['Datapoints']) / len(cpu_metrics['Datapoints'])
                    max_cpu = max(dp['Maximum'] for dp in cpu_metrics['Datapoints'])
                    
                    results['recent_activity'] = {
                        'avg_cpu_7_days': round(avg_cpu, 2),
                        'max_cpu_7_days': round(max_cpu, 2),
                        'data_points': len(cpu_metrics['Datapoints'])
                    }
                    
                    print(f"\n📊 Recent Activity (7 days):")
                    print(f"   Average CPU: {avg_cpu:.2f}%")
                    print(f"   Maximum CPU: {max_cpu:.2f}%")
                    print(f"   Data points: {len(cpu_metrics['Datapoints'])}")
                else:
                    results['recent_activity'] = {
                        'avg_cpu_7_days': 0,
                        'max_cpu_7_days': 0,
                        'data_points': 0
                    }
                    print(f"\n📊 No recent activity data found")
                    
            except Exception as e:
                print(f"⚠️  Could not get activity metrics: {e}")
                results['recent_activity'] = {'error': str(e)}
            
            # Generate recommendation
            recommendation = self._generate_recommendation(results)
            results['recommendation'] = recommendation
            
            print(f"\n💡 Recommendation: {recommendation['action']}")
            print(f"   Reason: {recommendation['reason']}")
            if 'estimated_savings' in recommendation:
                print(f"   Estimated monthly savings: ${recommendation['estimated_savings']}")
            
        except Exception as e:
            print(f"❌ Error analyzing cluster: {e}")
            results['error'] = str(e)
        
        return results
    
    def _generate_recommendation(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate recommendation based on analysis."""
        
        cluster_info = analysis.get('cluster_info', {})
        services = analysis.get('services', [])
        recent_activity = analysis.get('recent_activity', {})
        
        # Check if cluster is actually being used
        running_tasks = cluster_info.get('running_tasks', 0)
        active_services = cluster_info.get('active_services', 0)
        avg_cpu = recent_activity.get('avg_cpu_7_days', 0)
        
        # Analyze service configurations
        total_desired_count = sum(s.get('desired_count', 0) for s in services)
        total_running_count = sum(s.get('running_count', 0) for s in services)
        
        if running_tasks == 0 and active_services == 0:
            return {
                'action': 'SAFE_TO_DELETE',
                'reason': 'No running tasks or active services',
                'estimated_savings': 50  # Estimated based on idle resources
            }
        elif total_desired_count == 0 and total_running_count == 0:
            return {
                'action': 'SAFE_TO_DELETE',
                'reason': 'All services scaled to 0, no desired capacity',
                'estimated_savings': 30
            }
        elif avg_cpu < 1.0 and recent_activity.get('data_points', 0) > 0:
            return {
                'action': 'CONSIDER_DELETION',
                'reason': f'Very low CPU usage ({avg_cpu:.2f}%) over past 7 days',
                'estimated_savings': 40
            }
        elif recent_activity.get('data_points', 0) == 0:
            return {
                'action': 'LIKELY_UNUSED',
                'reason': 'No activity metrics found, possibly unused',
                'estimated_savings': 35
            }
        else:
            return {
                'action': 'KEEP_ACTIVE',
                'reason': f'Cluster appears to be in active use (CPU: {avg_cpu:.2f}%)',
                'estimated_savings': 0
            }

def main():
    """Main execution function."""
    
    import sys
    
    # Get cluster name from command line argument
    cluster_name = "multimodal-librarian-full-ml"  # default
    if len(sys.argv) > 1:
        cluster_name = sys.argv[1]
    
    analyzer = MLClusterAnalyzer(cluster_name)
    
    try:
        print("🔍 ML Cluster Usage Analysis")
        print("=" * 50)
        
        results = analyzer.analyze_cluster_details()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"ml-cluster-analysis-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed analysis saved to: {results_file}")
        
        # Return appropriate exit code
        recommendation = results.get('recommendation', {})
        if recommendation.get('action') in ['SAFE_TO_DELETE', 'CONSIDER_DELETION']:
            return 0  # Can be deleted
        else:
            return 1  # Should keep
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())