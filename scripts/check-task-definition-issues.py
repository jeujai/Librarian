#!/usr/bin/env python3
"""
Check task definition for issues preventing task startup.
"""

import boto3
import json
import sys
from datetime import datetime

def check_task_definition_issues():
    """Check task definition for issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        secretsmanager_client = boto3.client('secretsmanager', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'task_definition_analysis': {},
            'resource_checks': {},
            'recommendations': []
        }
        
        print("🔍 Checking Task Definition Issues")
        print("=" * 35)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get current task definition
        print("\n1. Analyzing Task Definition:")
        print("-" * 30)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not service_details['services']:
            print("❌ Service not found")
            return result
        
        service = service_details['services'][0]
        task_def_arn = service['taskDefinition']
        
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        
        print(f"📋 Task Definition: {task_def['family']}:{task_def['revision']}")
        print(f"   - CPU: {task_def.get('cpu', 'N/A')}")
        print(f"   - Memory: {task_def.get('memory', 'N/A')}")
        print(f"   - Network Mode: {task_def.get('networkMode', 'N/A')}")
        print(f"   - Requires Attributes: {len(task_def.get('requiresAttributes', []))}")
        
        # Check execution role
        execution_role = task_def.get('executionRoleArn')
        task_role = task_def.get('taskRoleArn')
        
        print(f"   - Execution Role: {execution_role}")
        print(f"   - Task Role: {task_role}")
        
        if not execution_role:
            result['recommendations'].append("No execution role specified - required for Fargate")
        
        result['task_definition_analysis'] = {
            'family': task_def['family'],
            'revision': task_def['revision'],
            'cpu': task_def.get('cpu'),
            'memory': task_def.get('memory'),
            'execution_role': execution_role,
            'task_role': task_role
        }
        
        # 2. Check container definitions
        print("\n2. Analyzing Container Definitions:")
        print("-" * 36)
        
        container_defs = task_def.get('containerDefinitions', [])
        
        for container_def in container_defs:
            container_name = container_def['name']
            image = container_def['image']
            
            print(f"📦 Container: {container_name}")
            print(f"   - Image: {image}")
            
            # Check memory and CPU
            memory = container_def.get('memory')
            memory_reservation = container_def.get('memoryReservation')
            cpu = container_def.get('cpu', 0)
            
            print(f"   - Memory: {memory} (Reservation: {memory_reservation})")
            print(f"   - CPU: {cpu}")
            
            # Check essential flag
            essential = container_def.get('essential', True)
            print(f"   - Essential: {essential}")
            
            # Check port mappings
            port_mappings = container_def.get('portMappings', [])
            print(f"   - Port Mappings: {len(port_mappings)}")
            for port in port_mappings:
                container_port = port.get('containerPort')
                host_port = port.get('hostPort')
                protocol = port.get('protocol', 'tcp')
                print(f"     - {host_port}:{container_port} ({protocol})")
            
            # Check environment variables
            env_vars = container_def.get('environment', [])
            secrets = container_def.get('secrets', [])
            
            print(f"   - Environment Variables: {len(env_vars)}")
            print(f"   - Secrets: {len(secrets)}")
            
            # Check secrets accessibility
            if secrets:
                print("   🔐 Checking Secrets Accessibility:")
                for secret in secrets:
                    secret_name = secret.get('name')
                    secret_arn = secret.get('valueFrom')
                    
                    print(f"     - {secret_name}: {secret_arn}")
                    
                    try:
                        # Try to access the secret
                        secret_response = secretsmanager_client.get_secret_value(
                            SecretId=secret_arn
                        )
                        print(f"       ✅ Secret accessible")
                    except Exception as e:
                        print(f"       ❌ Secret not accessible: {e}")
                        result['recommendations'].append(f"Secret {secret_arn} not accessible: {e}")
            
            # Check log configuration
            log_config = container_def.get('logConfiguration', {})
            if log_config:
                log_driver = log_config.get('logDriver')
                log_options = log_config.get('logOptions', {})
                log_group = log_options.get('awslogs-group')
                
                print(f"   - Log Driver: {log_driver}")
                print(f"   - Log Group: {log_group}")
                
                # Check if log group exists
                if log_group:
                    try:
                        logs_client.describe_log_groups(
                            logGroupNamePrefix=log_group,
                            limit=1
                        )
                        print(f"     ✅ Log group exists")
                    except Exception as e:
                        print(f"     ❌ Log group issue: {e}")
                        result['recommendations'].append(f"Log group {log_group} issue: {e}")
                else:
                    print(f"     ⚠️  No log group specified")
                    result['recommendations'].append("No log group specified in logging configuration")
            else:
                print(f"   - No logging configuration")
                result['recommendations'].append("No logging configuration specified")
        
        # 3. Check for recent task failures
        print("\n3. Checking Recent Task Failures:")
        print("-" * 34)
        
        # List recent tasks
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='STOPPED',
            maxResults=5
        )
        
        if tasks_response['taskArns']:
            print(f"📋 Found {len(tasks_response['taskArns'])} recent stopped tasks")
            
            task_details = ecs_client.describe_tasks(
                cluster=cluster_name,
                tasks=tasks_response['taskArns']
            )
            
            for task in task_details['tasks']:
                task_id = task['taskArn'].split('/')[-1]
                stop_reason = task.get('stoppedReason', 'Unknown')
                stop_code = task.get('stopCode', 'Unknown')
                
                print(f"   - Task {task_id}: {stop_reason} ({stop_code})")
                
                if 'ResourceInitializationError' in stop_reason:
                    result['recommendations'].append(f"Task {task_id} failed with ResourceInitializationError")
        else:
            print("📋 No recent stopped tasks found")
        
        # 4. Check current pending tasks in detail
        print("\n4. Checking Current Pending Tasks:")
        print("-" * 35)
        
        current_tasks = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='RUNNING'
        )
        
        if current_tasks['taskArns']:
            task_details = ecs_client.describe_tasks(
                cluster=cluster_name,
                tasks=current_tasks['taskArns']
            )
            
            for task in task_details['tasks']:
                task_id = task['taskArn'].split('/')[-1]
                status = task['lastStatus']
                created_at = task['createdAt']
                
                # Calculate how long task has been pending
                now = datetime.now(created_at.tzinfo)
                pending_duration = now - created_at
                
                print(f"   - Task {task_id}: {status} (pending for {pending_duration})")
                
                if pending_duration.total_seconds() > 600:  # More than 10 minutes
                    result['recommendations'].append(f"Task {task_id} has been pending for {pending_duration}")
        
        # 5. Summary and Recommendations
        print("\n5. Summary and Recommendations:")
        print("-" * 35)
        
        if result['recommendations']:
            print("🚨 Issues Found:")
            for i, rec in enumerate(result['recommendations'], 1):
                print(f"   {i}. {rec}")
        else:
            print("✅ No obvious task definition issues found")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = check_task_definition_issues()
    
    # Save analysis to file
    analysis_file = f"task-definition-analysis-{int(datetime.now().timestamp())}.json"
    with open(analysis_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Analysis saved to: {analysis_file}")
    
    if result.get('recommendations'):
        sys.exit(1)
    else:
        sys.exit(0)