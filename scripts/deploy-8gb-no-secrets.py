#!/usr/bin/env python3
"""
Deploy with 8GB memory using task definition 37 as base (no secrets).
"""

import boto3
import json
from datetime import datetime

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
TASK_FAMILY = "multimodal-lib-prod-app"
BASE_TASK_DEF = "multimodal-lib-prod-app:37"  # Working task definition
NEW_MEMORY_MB = 8192  # 8GB
NEW_CPU_UNITS = 4096  # 4 vCPUs

def main():
    print("🔧 Deploying with 8GB Memory (Based on Task Def 37)")
    print("=" * 60)
    
    ecs = boto3.client('ecs')
    
    # Get task definition 37 (the working one)
    print(f"📋 Fetching base task definition: {BASE_TASK_DEF}...")
    task_def_response = ecs.describe_task_definition(taskDefinition=BASE_TASK_DEF)
    current_task_def = task_def_response['taskDefinition']
    
    print(f"   Current Memory: {current_task_def.get('memory')} MB")
    print(f"   Current CPU: {current_task_def.get('cpu')} units")
    print(f"   Secrets: {current_task_def['containerDefinitions'][0].get('secrets', 'None')}")
    
    # Create new task definition with only memory/CPU changed
    new_task_def = {
        'family': current_task_def['family'],
        'taskRoleArn': current_task_def.get('taskRoleArn'),
        'executionRoleArn': current_task_def.get('executionRoleArn'),
        'networkMode': current_task_def['networkMode'],
        'requiresCompatibilities': current_task_def['requiresCompatibilities'],
        'cpu': str(NEW_CPU_UNITS),
        'memory': str(NEW_MEMORY_MB),
        'containerDefinitions': current_task_def['containerDefinitions']
    }
    
    if 'ephemeralStorage' in current_task_def:
        new_task_def['ephemeralStorage'] = current_task_def['ephemeralStorage']
    
    # Register new task definition
    print(f"\n📝 Registering new task definition...")
    print(f"   Memory: {NEW_MEMORY_MB} MB (8GB)")
    print(f"   CPU: {NEW_CPU_UNITS} units")
    print(f"   Based on working task def 37")
    
    register_response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    new_revision = register_response['taskDefinition']['revision']
    
    print(f"✅ New task definition registered")
    print(f"   ARN: {new_task_def_arn}")
    print(f"   Revision: {new_revision}")
    
    # Update service
    print(f"\n🚀 Updating service...")
    ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"✅ Service update initiated")
    print(f"\n📊 Monitor deployment with:")
    print(f"   aws ecs describe-services --cluster {CLUSTER_NAME} --services {SERVICE_NAME}")
    
    # Save results
    timestamp = int(datetime.now().timestamp())
    results = {
        'timestamp': datetime.now().isoformat(),
        'base_task_definition': BASE_TASK_DEF,
        'new_task_definition_arn': new_task_def_arn,
        'new_revision': new_revision,
        'memory_mb': NEW_MEMORY_MB,
        'cpu_units': NEW_CPU_UNITS
    }
    
    results_file = f'8gb-deployment-no-secrets-{timestamp}.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📝 Results saved to: {results_file}")

if __name__ == "__main__":
    main()
