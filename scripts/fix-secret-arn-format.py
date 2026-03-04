#!/usr/bin/env python3
"""
Fix secret ARN format in task definition.
"""

import boto3
import json
import sys
from datetime import datetime

def fix_secret_arn_format():
    """Fix secret ARN format in task definition."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing Secret ARN Format")
        print("=" * 30)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get current task definition
        print("\n1. Getting Current Task Definition:")
        print("-" * 36)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_details['services'][0]
        current_task_def_arn = service['taskDefinition']
        
        task_def_response = ecs_client.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        current_task_def = task_def_response['taskDefinition']
        
        print(f"📋 Current Task Definition: {current_task_def['family']}:{current_task_def['revision']}")
        
        # 2. Create fixed task definition
        print("\n2. Creating Fixed Task Definition:")
        print("-" * 35)
        
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
                    
                    # Remove any field specifiers - just use the base secret ARN
                    if ':endpoint' in secret_arn:
                        base_secret_arn = secret_arn.split(':endpoint')[0]
                        print(f"   - Fixed secret: {secret_name} = {base_secret_arn}")
                        
                        fixed_secrets.append({
                            'name': secret_name,
                            'valueFrom': base_secret_arn
                        })
                        
                        result['fix_actions'].append(f"Fixed secret {secret_name}: removed field specifier")
                    else:
                        # Secret ARN is already correct
                        fixed_secrets.append(secret)
                
                fixed_container['secrets'] = fixed_secrets
            
            new_task_def['containerDefinitions'].append(fixed_container)
        
        # 3. Register new task definition
        print("\n3. Registering New Task Definition:")
        print("-" * 36)
        
        try:
            register_response = ecs_client.register_task_definition(**new_task_def)
            
            new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
            new_revision = register_response['taskDefinition']['revision']
            
            print(f"✅ Registered new task definition: {current_task_def['family']}:{new_revision}")
            
            result['fix_actions'].append(f"Registered new task definition revision {new_revision}")
            
        except Exception as e:
            print(f"❌ Error registering task definition: {e}")
            result['fix_actions'].append(f"Error registering task definition: {e}")
            return result
        
        # 4. Update service
        print("\n4. Updating Service:")
        print("-" * 18)
        
        try:
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                taskDefinition=new_task_def_arn,
                forceNewDeployment=True
            )
            
            print("✅ Service updated with fixed task definition")
            result['fix_actions'].append("Updated service with fixed task definition")
            result['success'] = True
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_secret_arn_format()
    
    # Save result to file
    result_file = f"secret-arn-format-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Secret ARN format successfully fixed!")
        sys.exit(0)
    else:
        print("\n⚠️  Secret ARN format fix needs attention")
        sys.exit(1)