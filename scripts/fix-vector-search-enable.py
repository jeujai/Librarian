#!/usr/bin/env python3
"""
Fix ENABLE_VECTOR_SEARCH environment variable to enable vector search
"""

import boto3
import json
import sys

# AWS clients
ecs = boto3.client('ecs')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TASK_FAMILY = 'multimodal-lib-prod-app'

def main():
    print("=" * 80)
    print("🔧 Fixing ENABLE_VECTOR_SEARCH Configuration")
    print("=" * 80)
    
    try:
        # Get current task definition
        print(f"\n📋 Getting current task definition...")
        response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
        task_def = response['taskDefinition']
        
        print(f"✅ Current: {task_def['taskDefinitionArn']}")
        
        # Update environment variables
        container_def = task_def['containerDefinitions'][0]
        env_vars = container_def.get('environment', [])
        
        # Find and update ENABLE_VECTOR_SEARCH
        updated = False
        for var in env_vars:
            if var['name'] == 'ENABLE_VECTOR_SEARCH':
                old_value = var['value']
                var['value'] = 'true'
                print(f"\n🔧 Updated ENABLE_VECTOR_SEARCH: {old_value} → true")
                updated = True
                break
        
        if not updated:
            # Add if not found
            env_vars.append({'name': 'ENABLE_VECTOR_SEARCH', 'value': 'true'})
            print(f"\n➕ Added ENABLE_VECTOR_SEARCH=true")
        
        container_def['environment'] = env_vars
        
        # Remove fields that can't be used in register_task_definition
        fields_to_remove = [
            'taskDefinitionArn',
            'revision',
            'status',
            'requiresAttributes',
            'compatibilities',
            'registeredAt',
            'registeredBy'
        ]
        
        for field in fields_to_remove:
            task_def.pop(field, None)
        
        # Register new task definition
        print(f"\n📝 Registering new task definition...")
        response = ecs.register_task_definition(**task_def)
        new_task_def = response['taskDefinition']
        
        print(f"✅ New task definition: {new_task_def['taskDefinitionArn']}")
        
        # Update service
        print(f"\n🚀 Updating service...")
        response = ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            taskDefinition=new_task_def['taskDefinitionArn'],
            forceNewDeployment=True
        )
        
        print(f"✅ Service updated successfully")
        
        # Wait for deployment
        print(f"\n⏳ Waiting for deployment to stabilize...")
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME],
            WaiterConfig={'Delay': 15, 'MaxAttempts': 40}
        )
        
        print(f"✅ Deployment stabilized!")
        
        print("\n" + "=" * 80)
        print("✅ Vector search enabled successfully!")
        print("=" * 80)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
