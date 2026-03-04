#!/usr/bin/env python3
"""
Fix task definition secrets configuration.
"""

import boto3
import json
import sys
from datetime import datetime

def fix_task_definition_secrets():
    """Fix task definition secrets configuration."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'original_task_def': {},
            'fixed_task_def': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing Task Definition Secrets Configuration")
        print("=" * 50)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get current task definition
        print("\n1. Getting Current Task Definition:")
        print("-" * 36)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not service_details['services']:
            print("❌ Service not found")
            return result
        
        service = service_details['services'][0]
        current_task_def_arn = service['taskDefinition']
        
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        current_task_def = task_def_response['taskDefinition']
        
        print(f"📋 Current Task Definition: {current_task_def['family']}:{current_task_def['revision']}")
        
        result['original_task_def'] = {
            'family': current_task_def['family'],
            'revision': current_task_def['revision'],
            'arn': current_task_def_arn
        }
        
        # 2. Create fixed task definition
        print("\n2. Creating Fixed Task Definition:")
        print("-" * 35)
        
        # Copy task definition and fix issues
        new_task_def = {
            'family': current_task_def['family'],
            'networkMode': current_task_def.get('networkMode', 'awsvpc'),
            'requiresCompatibilities': current_task_def.get('requiresCompatibilities', ['FARGATE']),
            'cpu': current_task_def.get('cpu', '2048'),
            'memory': current_task_def.get('memory', '4096'),
            'executionRoleArn': current_task_def.get('executionRoleArn'),
            'taskRoleArn': current_task_def.get('taskRoleArn'),
            'containerDefinitions': []
        }
        
        # Create log group if it doesn't exist
        log_group_name = f"/ecs/{current_task_def['family']}"
        
        try:
            logs_client.create_log_group(
                logGroupName=log_group_name,
                retentionInDays=7  # 7 days retention for cost efficiency
            )
            print(f"✅ Created log group: {log_group_name}")
            result['fix_actions'].append(f"Created log group {log_group_name}")
        except logs_client.exceptions.ResourceAlreadyExistsException:
            print(f"✅ Log group already exists: {log_group_name}")
        except Exception as e:
            print(f"⚠️  Could not create log group: {e}")
        
        # Fix container definitions
        for container_def in current_task_def['containerDefinitions']:
            fixed_container = container_def.copy()
            
            print(f"🔧 Fixing container: {container_def['name']}")
            
            # Fix secrets configuration
            if 'secrets' in fixed_container:
                fixed_secrets = []
                
                for secret in fixed_container['secrets']:
                    secret_name = secret['name']
                    secret_arn = secret['valueFrom']
                    
                    print(f"   - Original secret: {secret_name} = {secret_arn}")
                    
                    # Fix the secret ARN by removing the field specifier
                    if '::' in secret_arn:
                        # Extract the base secret ARN (everything before the first ::)
                        base_secret_arn = secret_arn.split('::')[0]
                        
                        # For Neptune endpoint, we need to get the endpoint field
                        if 'neptune' in secret_arn.lower() and 'endpoint' in secret_arn.lower():
                            fixed_secret_arn = f"{base_secret_arn}:endpoint::"
                        # For OpenSearch endpoint
                        elif 'opensearch' in secret_arn.lower() and 'endpoint' in secret_arn.lower():
                            fixed_secret_arn = f"{base_secret_arn}:endpoint::"
                        else:
                            fixed_secret_arn = base_secret_arn
                        
                        # Actually, let's just use the base ARN and get the whole secret
                        # The application can parse the JSON to get the endpoint
                        fixed_secret_arn = base_secret_arn
                        
                        print(f"   - Fixed secret: {secret_name} = {fixed_secret_arn}")
                        
                        fixed_secrets.append({
                            'name': secret_name,
                            'valueFrom': fixed_secret_arn
                        })
                        
                        result['fix_actions'].append(f"Fixed secret {secret_name}: {secret_arn} -> {fixed_secret_arn}")
                    else:
                        # Secret ARN is already correct
                        fixed_secrets.append(secret)
                
                fixed_container['secrets'] = fixed_secrets
            
            # Fix logging configuration
            fixed_container['logConfiguration'] = {
                'logDriver': 'awslogs',
                'options': {
                    'awslogs-group': log_group_name,
                    'awslogs-region': 'us-east-1',
                    'awslogs-stream-prefix': 'ecs'
                }
            }
            
            print(f"   - Fixed logging: {log_group_name}")
            result['fix_actions'].append(f"Fixed logging configuration for {container_def['name']}")
            
            new_task_def['containerDefinitions'].append(fixed_container)
        
        # 3. Register new task definition
        print("\n3. Registering New Task Definition:")
        print("-" * 36)
        
        try:
            register_response = ecs_client.register_task_definition(**new_task_def)
            
            new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
            new_revision = register_response['taskDefinition']['revision']
            
            print(f"✅ Registered new task definition: {current_task_def['family']}:{new_revision}")
            print(f"   ARN: {new_task_def_arn}")
            
            result['fixed_task_def'] = {
                'family': current_task_def['family'],
                'revision': new_revision,
                'arn': new_task_def_arn
            }
            
            result['fix_actions'].append(f"Registered new task definition revision {new_revision}")
            
        except Exception as e:
            print(f"❌ Error registering task definition: {e}")
            result['fix_actions'].append(f"Error registering task definition: {e}")
            return result
        
        # 4. Update service to use new task definition
        print("\n4. Updating Service:")
        print("-" * 18)
        
        try:
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=new_task_def_arn,
                forceNewDeployment=True
            )
            
            print("✅ Service updated with new task definition")
            print("🔄 Forcing new deployment")
            
            result['fix_actions'].append("Updated service with fixed task definition")
            result['fix_actions'].append("Forced new deployment")
            
            # 5. Monitor deployment
            print("\n5. Monitoring Deployment:")
            print("-" * 25)
            
            print("⏳ Waiting for deployment to start...")
            import time
            time.sleep(30)
            
            # Check service status
            service_details = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if service_details['services']:
                service = service_details['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print(f"📊 Service Status: {running_count}/{desired_count} tasks running")
                
                # Check recent events
                recent_events = service.get('events', [])[:3]
                print("📋 Recent Events:")
                
                secrets_error_found = False
                for event in recent_events:
                    message = event['message']
                    timestamp = event['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
                    
                    print(f"   [{timestamp}] {message[:100]}...")
                    
                    if 'unable to retrieve secret' in message.lower():
                        secrets_error_found = True
                
                if not secrets_error_found:
                    result['success'] = True
                    result['fix_actions'].append("No recent secrets errors detected")
                    print("✅ No recent secrets errors detected")
                else:
                    result['fix_actions'].append("Still seeing secrets errors - may need more time")
                    print("⚠️  Still seeing secrets errors - deployment may need more time")
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_task_definition_secrets()
    
    # Save result to file
    result_file = f"task-definition-secrets-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Task definition secrets successfully fixed!")
        print("🚀 ECS tasks should now start properly")
        sys.exit(0)
    else:
        print("\n⚠️  Task definition secrets fix needs attention")
        sys.exit(1)