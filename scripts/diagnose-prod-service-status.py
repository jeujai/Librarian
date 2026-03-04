#!/usr/bin/env python3
"""
Diagnose Production Service Status

This script provides detailed analysis of the multimodal-lib-prod-service
to understand why it's scaled to 0 and what needs to be done to get it running.
"""

import boto3
import json
import time
from typing import Dict, List, Any
from datetime import datetime, timedelta

class ProdServiceDiagnostic:
    """Diagnose the production service status and scaling issues."""
    
    def __init__(self):
        self.session = boto3.Session()
        self.cluster_name = "multimodal-lib-prod-cluster"
        self.service_name = "multimodal-lib-prod-service"
        
    def diagnose_service_status(self) -> Dict[str, Any]:
        """Get comprehensive diagnosis of the production service."""
        
        results = {
            'service_info': {},
            'task_definition': {},
            'scaling_history': [],
            'deployment_history': [],
            'health_checks': {},
            'load_balancer_status': {},
            'recent_events': [],
            'recommendations': []
        }
        
        try:
            ecs = self.session.client('ecs', region_name='us-east-1')
            
            print("🔍 Diagnosing Production Service Status")
            print("=" * 60)
            
            # Get service details
            service_response = ecs.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if not service_response['services']:
                print(f"❌ Service '{self.service_name}' not found in cluster '{self.cluster_name}'")
                results['error'] = f"Service not found"
                return results
            
            service = service_response['services'][0]
            results['service_info'] = {
                'name': service['serviceName'],
                'status': service['status'],
                'running_count': service['runningCount'],
                'pending_count': service['pendingCount'],
                'desired_count': service['desiredCount'],
                'task_definition': service['taskDefinition'],
                'platform_version': service.get('platformVersion', 'N/A'),
                'launch_type': service.get('launchType', 'N/A'),
                'created_at': service['createdAt'].isoformat(),
                'updated_at': service.get('updatedAt', service['createdAt']).isoformat(),
                'deployment_status': service.get('deploymentController', {}).get('type', 'ECS')
            }
            
            print(f"📋 Service: {service['serviceName']}")
            print(f"   Status: {service['status']}")
            print(f"   Desired Count: {service['desiredCount']}")
            print(f"   Running Count: {service['runningCount']}")
            print(f"   Pending Count: {service['pendingCount']}")
            print(f"   Task Definition: {service['taskDefinition'].split('/')[-1]}")
            print(f"   Platform Version: {service.get('platformVersion', 'N/A')}")
            print(f"   Launch Type: {service.get('launchType', 'N/A')}")
            
            # Get task definition details
            task_def_arn = service['taskDefinition']
            task_def_response = ecs.describe_task_definition(taskDefinition=task_def_arn)
            
            if 'taskDefinition' in task_def_response:
                td = task_def_response['taskDefinition']
                results['task_definition'] = {
                    'family': td['family'],
                    'revision': td['revision'],
                    'status': td['status'],
                    'cpu': td.get('cpu', 'N/A'),
                    'memory': td.get('memory', 'N/A'),
                    'network_mode': td.get('networkMode', 'N/A'),
                    'requires_compatibilities': td.get('requiresCompatibilities', []),
                    'execution_role': td.get('executionRoleArn', 'N/A'),
                    'task_role': td.get('taskRoleArn', 'N/A'),
                    'container_count': len(td.get('containerDefinitions', [])),
                    'containers': []
                }
                
                print(f"\n📦 Task Definition: {td['family']}:{td['revision']}")
                print(f"   Status: {td['status']}")
                print(f"   CPU/Memory: {td.get('cpu', 'N/A')}/{td.get('memory', 'N/A')}")
                print(f"   Network Mode: {td.get('networkMode', 'N/A')}")
                print(f"   Compatibility: {', '.join(td.get('requiresCompatibilities', []))}")
                
                # Analyze containers
                for container in td.get('containerDefinitions', []):
                    container_info = {
                        'name': container['name'],
                        'image': container['image'],
                        'cpu': container.get('cpu', 0),
                        'memory': container.get('memory', container.get('memoryReservation', 'N/A')),
                        'essential': container.get('essential', True),
                        'port_mappings': container.get('portMappings', []),
                        'environment': len(container.get('environment', [])),
                        'secrets': len(container.get('secrets', [])),
                        'health_check': 'healthCheck' in container
                    }
                    results['task_definition']['containers'].append(container_info)
                    
                    print(f"\n   🐳 Container: {container['name']}")
                    print(f"      Image: {container['image']}")
                    print(f"      CPU/Memory: {container.get('cpu', 0)}/{container_info['memory']}")
                    print(f"      Essential: {container.get('essential', True)}")
                    print(f"      Ports: {len(container.get('portMappings', []))}")
                    print(f"      Environment Variables: {len(container.get('environment', []))}")
                    print(f"      Secrets: {len(container.get('secrets', []))}")
                    print(f"      Health Check: {'Yes' if 'healthCheck' in container else 'No'}")
            
            # Get service events (recent issues)
            events = service.get('events', [])[:10]  # Last 10 events
            results['recent_events'] = []
            
            if events:
                print(f"\n📅 Recent Service Events:")
                for event in events:
                    event_info = {
                        'created_at': event['createdAt'].isoformat(),
                        'message': event['message']
                    }
                    results['recent_events'].append(event_info)
                    print(f"   {event['createdAt'].strftime('%Y-%m-%d %H:%M:%S')}: {event['message']}")
            
            # Check deployments
            deployments = service.get('deployments', [])
            results['deployment_history'] = []
            
            if deployments:
                print(f"\n🚀 Deployment Status:")
                for deployment in deployments:
                    deployment_info = {
                        'id': deployment['id'],
                        'status': deployment['status'],
                        'task_definition': deployment['taskDefinition'],
                        'desired_count': deployment['desiredCount'],
                        'pending_count': deployment['pendingCount'],
                        'running_count': deployment['runningCount'],
                        'created_at': deployment['createdAt'].isoformat(),
                        'updated_at': deployment.get('updatedAt', deployment['createdAt']).isoformat()
                    }
                    results['deployment_history'].append(deployment_info)
                    
                    print(f"   Deployment {deployment['id'][:8]}...")
                    print(f"      Status: {deployment['status']}")
                    print(f"      Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
                    print(f"      Desired/Running: {deployment['desiredCount']}/{deployment['runningCount']}")
            
            # Check load balancer status
            load_balancers = service.get('loadBalancers', [])
            if load_balancers:
                print(f"\n⚖️  Load Balancer Configuration:")
                elbv2 = self.session.client('elbv2', region_name='us-east-1')
                
                for lb in load_balancers:
                    lb_info = {
                        'target_group_arn': lb.get('targetGroupArn', 'N/A'),
                        'container_name': lb.get('containerName', 'N/A'),
                        'container_port': lb.get('containerPort', 'N/A')
                    }
                    
                    print(f"   Target Group: {lb.get('targetGroupArn', 'N/A').split('/')[-1] if lb.get('targetGroupArn') else 'N/A'}")
                    print(f"   Container: {lb.get('containerName', 'N/A')}:{lb.get('containerPort', 'N/A')}")
                    
                    # Get target group health
                    if lb.get('targetGroupArn'):
                        try:
                            health_response = elbv2.describe_target_health(
                                TargetGroupArn=lb['targetGroupArn']
                            )
                            
                            healthy_targets = len([t for t in health_response['TargetHealthDescriptions'] 
                                                 if t['TargetHealth']['State'] == 'healthy'])
                            total_targets = len(health_response['TargetHealthDescriptions'])
                            
                            lb_info['healthy_targets'] = healthy_targets
                            lb_info['total_targets'] = total_targets
                            
                            print(f"   Health: {healthy_targets}/{total_targets} targets healthy")
                            
                            if total_targets > 0:
                                for target in health_response['TargetHealthDescriptions']:
                                    state = target['TargetHealth']['State']
                                    reason = target['TargetHealth'].get('Reason', 'N/A')
                                    print(f"      Target {target['Target']['Id']}: {state} ({reason})")
                        
                        except Exception as e:
                            print(f"   ⚠️  Could not get target group health: {e}")
                            lb_info['health_error'] = str(e)
                    
                    results['load_balancer_status'] = lb_info
            
            # Check Auto Scaling
            try:
                autoscaling = self.session.client('application-autoscaling', region_name='us-east-1')
                
                scalable_targets = autoscaling.describe_scalable_targets(
                    ServiceNamespace='ecs',
                    ResourceIds=[f'service/{self.cluster_name}/{self.service_name}']
                )
                
                if scalable_targets['ScalableTargets']:
                    target = scalable_targets['ScalableTargets'][0]
                    print(f"\n📈 Auto Scaling Configuration:")
                    print(f"   Min Capacity: {target['MinCapacity']}")
                    print(f"   Max Capacity: {target['MaxCapacity']}")
                    print(f"   Current Capacity: {target.get('CurrentCapacity', 'N/A')}")
                    print(f"   Role ARN: {target['RoleARN'].split('/')[-1]}")
                    
                    results['scaling_history'] = {
                        'min_capacity': target['MinCapacity'],
                        'max_capacity': target['MaxCapacity'],
                        'current_capacity': target.get('CurrentCapacity', 'N/A'),
                        'role_arn': target['RoleARN']
                    }
                else:
                    print(f"\n📈 Auto Scaling: Not configured")
                    
            except Exception as e:
                print(f"\n📈 Auto Scaling: Could not retrieve info ({e})")
            
            # Generate recommendations
            recommendations = self._generate_recommendations(results)
            results['recommendations'] = recommendations
            
            print(f"\n💡 Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec['action']}")
                print(f"      Reason: {rec['reason']}")
                if 'command' in rec:
                    print(f"      Command: {rec['command']}")
                print()
            
        except Exception as e:
            print(f"❌ Error during diagnosis: {e}")
            results['error'] = str(e)
        
        return results
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on analysis."""
        
        recommendations = []
        service_info = analysis.get('service_info', {})
        task_def = analysis.get('task_definition', {})
        events = analysis.get('recent_events', [])
        
        # Check if service is scaled to 0
        if service_info.get('desired_count', 0) == 0:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'Scale up the service to at least 1 instance',
                'reason': 'Service is currently scaled to 0 (desired count = 0)',
                'command': f'aws ecs update-service --cluster {self.cluster_name} --service {self.service_name} --desired-count 1'
            })
        
        # Check task definition status
        if task_def.get('status') == 'INACTIVE':
            recommendations.append({
                'priority': 'HIGH',
                'action': 'Update to an active task definition',
                'reason': 'Current task definition is INACTIVE',
                'command': 'Create a new task definition revision or reactivate the current one'
            })
        
        # Check for recent deployment failures
        deployment_failures = [e for e in events if 'failed' in e.get('message', '').lower() or 'error' in e.get('message', '').lower()]
        if deployment_failures:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'Investigate recent deployment failures',
                'reason': f'Found {len(deployment_failures)} recent failure events',
                'command': 'Check service events and CloudWatch logs for detailed error messages'
            })
        
        # Check container health checks
        containers_without_health_checks = [c for c in task_def.get('containers', []) if not c.get('health_check')]
        if containers_without_health_checks:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'Add health checks to containers',
                'reason': f'{len(containers_without_health_checks)} containers lack health checks',
                'command': 'Update task definition to include health check configurations'
            })
        
        # Check load balancer health
        lb_status = analysis.get('load_balancer_status', {})
        if lb_status and lb_status.get('healthy_targets', 0) == 0 and lb_status.get('total_targets', 0) > 0:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'Fix load balancer target health issues',
                'reason': 'No healthy targets in load balancer target group',
                'command': 'Check target group health checks and container port configuration'
            })
        
        # Check resource allocation
        if task_def.get('cpu') == 'N/A' or task_def.get('memory') == 'N/A':
            recommendations.append({
                'priority': 'MEDIUM',
                'action': 'Ensure proper CPU and memory allocation',
                'reason': 'Task definition may be missing CPU/memory specifications',
                'command': 'Update task definition with explicit CPU and memory values'
            })
        
        # If no specific issues found but service is down
        if not recommendations and service_info.get('desired_count', 0) > 0 and service_info.get('running_count', 0) == 0:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'Investigate why tasks are not starting',
                'reason': 'Service has desired count > 0 but no running tasks',
                'command': 'Check CloudWatch logs and ECS task stopped reasons'
            })
        
        return recommendations

def main():
    """Main execution function."""
    
    diagnostic = ProdServiceDiagnostic()
    
    try:
        results = diagnostic.diagnose_service_status()
        
        # Save detailed results
        timestamp = int(time.time())
        results_file = f"prod-service-diagnosis-{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n📄 Detailed diagnosis saved to: {results_file}")
        
        # Return appropriate exit code based on service health
        service_info = results.get('service_info', {})
        if service_info.get('running_count', 0) > 0:
            print("\n✅ Service appears to be running")
            return 0
        elif service_info.get('desired_count', 0) == 0:
            print("\n⚠️  Service is intentionally scaled to 0")
            return 1
        else:
            print("\n❌ Service has issues that need attention")
            return 2
        
    except Exception as e:
        print(f"❌ Diagnosis failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())