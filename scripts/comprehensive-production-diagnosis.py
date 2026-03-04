#!/usr/bin/env python3
"""
Comprehensive production environment diagnosis and fix strategy.
"""

import boto3
import json
import sys
from datetime import datetime

def comprehensive_production_diagnosis():
    """Perform comprehensive diagnosis of production issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        secretsmanager_client = boto3.client('secretsmanager', region_name='us-east-1')
        
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'critical_issues': [],
            'infrastructure_status': {},
            'task_failures': [],
            'recommendations': []
        }
        
        print("🔍 COMPREHENSIVE PRODUCTION DIAGNOSIS")
        print("=" * 50)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Check if basic infrastructure exists
        print("\n1. INFRASTRUCTURE EXISTENCE CHECK:")
        print("-" * 40)
        
        # Check cluster
        try:
            clusters = ecs_client.describe_clusters(clusters=[cluster_name])
            if clusters['clusters']:
                cluster = clusters['clusters'][0]
                print(f"✅ ECS Cluster: {cluster_name} - {cluster['status']}")
                diagnosis['infrastructure_status']['cluster'] = {
                    'exists': True,
                    'status': cluster['status'],
                    'active_services': cluster['activeServicesCount'],
                    'running_tasks': cluster['runningTasksCount'],
                    'pending_tasks': cluster['pendingTasksCount']
                }
            else:
                print(f"❌ ECS Cluster: {cluster_name} - NOT FOUND")
                diagnosis['critical_issues'].append(f"ECS cluster {cluster_name} does not exist")
                diagnosis['infrastructure_status']['cluster'] = {'exists': False}
        except Exception as e:
            print(f"❌ ECS Cluster check failed: {e}")
            diagnosis['critical_issues'].append(f"Cannot access ECS cluster: {e}")
        
        # Check service
        try:
            services = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            if services['services']:
                service = services['services'][0]
                print(f"✅ ECS Service: {service_name} - {service['status']}")
                print(f"   Running: {service['runningCount']}/{service['desiredCount']}")
                diagnosis['infrastructure_status']['service'] = {
                    'exists': True,
                    'status': service['status'],
                    'running_count': service['runningCount'],
                    'desired_count': service['desiredCount'],
                    'task_definition': service['taskDefinition']
                }
            else:
                print(f"❌ ECS Service: {service_name} - NOT FOUND")
                diagnosis['critical_issues'].append(f"ECS service {service_name} does not exist")
                diagnosis['infrastructure_status']['service'] = {'exists': False}
        except Exception as e:
            print(f"❌ ECS Service check failed: {e}")
            diagnosis['critical_issues'].append(f"Cannot access ECS service: {e}")
        
        # Check load balancer
        try:
            lbs = elb_client.describe_load_balancers()
            multimodal_lb = None
            for lb in lbs['LoadBalancers']:
                if 'multimodal' in lb['LoadBalancerName'].lower():
                    multimodal_lb = lb
                    break
            
            if multimodal_lb:
                print(f"✅ Load Balancer: {multimodal_lb['LoadBalancerName']} - {multimodal_lb['State']['Code']}")
                diagnosis['infrastructure_status']['load_balancer'] = {
                    'exists': True,
                    'name': multimodal_lb['LoadBalancerName'],
                    'state': multimodal_lb['State']['Code'],
                    'dns_name': multimodal_lb['DNSName'],
                    'vpc_id': multimodal_lb['VpcId']
                }
            else:
                print("❌ Load Balancer: NOT FOUND")
                diagnosis['critical_issues'].append("No multimodal load balancer found")
                diagnosis['infrastructure_status']['load_balancer'] = {'exists': False}
        except Exception as e:
            print(f"❌ Load Balancer check failed: {e}")
            diagnosis['critical_issues'].append(f"Cannot access load balancer: {e}")
        
        # 2. Analyze recent task failures
        print("\n2. TASK FAILURE ANALYSIS:")
        print("-" * 30)
        
        try:
            # Get stopped tasks
            stopped_tasks = ecs_client.list_tasks(
                cluster=cluster_name,
                serviceName=service_name,
                desiredStatus='STOPPED',
                maxResults=10
            )
            
            if stopped_tasks['taskArns']:
                task_details = ecs_client.describe_tasks(
                    cluster=cluster_name,
                    tasks=stopped_tasks['taskArns']
                )
                
                failure_reasons = {}
                
                for task in task_details['tasks']:
                    task_id = task['taskArn'].split('/')[-1]
                    stop_reason = task.get('stoppedReason', 'Unknown')
                    stop_code = task.get('stopCode', 'Unknown')
                    
                    print(f"📋 Task {task_id}: {stop_code} - {stop_reason[:100]}...")
                    
                    # Categorize failures
                    if 'ResourceInitializationError' in stop_reason:
                        if 'secrets' in stop_reason.lower():
                            failure_type = 'secrets_access'
                        elif 'pull' in stop_reason.lower() or 'registry' in stop_reason.lower():
                            failure_type = 'container_pull'
                        elif 'log' in stop_reason.lower():
                            failure_type = 'logging'
                        else:
                            failure_type = 'resource_initialization'
                    elif 'CannotPullContainerError' in stop_reason:
                        failure_type = 'container_pull'
                    else:
                        failure_type = 'other'
                    
                    if failure_type not in failure_reasons:
                        failure_reasons[failure_type] = 0
                    failure_reasons[failure_type] += 1
                    
                    diagnosis['task_failures'].append({
                        'task_id': task_id,
                        'stop_code': stop_code,
                        'stop_reason': stop_reason,
                        'failure_type': failure_type
                    })
                
                print(f"\n📊 Failure Summary:")
                for failure_type, count in failure_reasons.items():
                    print(f"   - {failure_type}: {count} tasks")
                    
                    if failure_type == 'secrets_access':
                        diagnosis['critical_issues'].append("Tasks cannot access AWS Secrets Manager")
                    elif failure_type == 'container_pull':
                        diagnosis['critical_issues'].append("Tasks cannot pull container images from ECR")
                    elif failure_type == 'logging':
                        diagnosis['critical_issues'].append("Tasks cannot create CloudWatch log streams")
            else:
                print("📋 No recent stopped tasks found")
        
        except Exception as e:
            print(f"❌ Task failure analysis failed: {e}")
            diagnosis['critical_issues'].append(f"Cannot analyze task failures: {e}")
        
        # 3. Check critical resources
        print("\n3. CRITICAL RESOURCE CHECK:")
        print("-" * 32)
        
        # Check secrets
        try:
            secrets = [
                'multimodal-lib-prod/neptune/connection',
                'multimodal-lib-prod/opensearch/connection'
            ]
            
            for secret_name in secrets:
                try:
                    secret_response = secretsmanager_client.describe_secret(
                        SecretId=secret_name
                    )
                    print(f"✅ Secret: {secret_name}")
                except secretsmanager_client.exceptions.ResourceNotFoundException:
                    print(f"❌ Secret: {secret_name} - NOT FOUND")
                    diagnosis['critical_issues'].append(f"Secret {secret_name} does not exist")
                except Exception as e:
                    print(f"❌ Secret: {secret_name} - ERROR: {e}")
                    diagnosis['critical_issues'].append(f"Cannot access secret {secret_name}: {e}")
        
        except Exception as e:
            print(f"❌ Secrets check failed: {e}")
        
        # Check log group
        try:
            log_group_name = "/ecs/multimodal-lib-prod-app"
            logs_client.describe_log_groups(
                logGroupNamePrefix=log_group_name,
                limit=1
            )
            print(f"✅ Log Group: {log_group_name}")
        except Exception as e:
            print(f"❌ Log Group: {log_group_name} - ERROR: {e}")
            diagnosis['critical_issues'].append(f"Log group {log_group_name} issue: {e}")
        
        # 4. Generate recommendations
        print("\n4. RECOMMENDATIONS:")
        print("-" * 20)
        
        if not diagnosis['infrastructure_status'].get('cluster', {}).get('exists'):
            diagnosis['recommendations'].append("CRITICAL: Create ECS cluster")
        
        if not diagnosis['infrastructure_status'].get('service', {}).get('exists'):
            diagnosis['recommendations'].append("CRITICAL: Create ECS service")
        
        if not diagnosis['infrastructure_status'].get('load_balancer', {}).get('exists'):
            diagnosis['recommendations'].append("CRITICAL: Create load balancer")
        
        # Analyze failure patterns
        failure_types = set()
        for failure in diagnosis['task_failures']:
            failure_types.add(failure['failure_type'])
        
        if 'secrets_access' in failure_types:
            diagnosis['recommendations'].append("Fix secrets access: Check VPC endpoints and IAM permissions")
        
        if 'container_pull' in failure_types:
            diagnosis['recommendations'].append("Fix container pull: Check ECR access and VPC endpoints")
        
        if 'logging' in failure_types:
            diagnosis['recommendations'].append("Fix logging: Ensure log group exists and IAM permissions")
        
        # Print recommendations
        for i, rec in enumerate(diagnosis['recommendations'], 1):
            print(f"   {i}. {rec}")
        
        return diagnosis
        
    except Exception as e:
        print(f"❌ Comprehensive diagnosis failed: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = comprehensive_production_diagnosis()
    
    # Save diagnosis to file
    diagnosis_file = f"comprehensive-production-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(diagnosis_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Comprehensive diagnosis saved to: {diagnosis_file}")
    
    if result.get('critical_issues'):
        print(f"\n🚨 CRITICAL ISSUES FOUND: {len(result['critical_issues'])}")
        for issue in result['critical_issues']:
            print(f"   - {issue}")
        sys.exit(1)
    else:
        print("\n✅ No critical issues found")
        sys.exit(0)