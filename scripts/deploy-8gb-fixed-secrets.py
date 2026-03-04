#!/usr/bin/env python3
"""
Deploy with 8GB memory and fixed secrets configuration.
"""

import boto3
import json
from datetime import datetime

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
TASK_FAMILY = "multimodal-lib-prod-app"
NEW_MEMORY_MB = 8192  # 8GB
NEW_CPU_UNITS = 4096  # 4 vCPUs

def main():
    print("🔧 Deploying with 8GB Memory and Fixed Secrets")
    print("=" * 60)
    
    ecs = boto3.client('ecs')
    
    # Get current task definition
    print("📋 Fetching current task definition...")
    task_def_response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
    current_task_def = task_def_response['taskDefinition']
    
    # Fix secrets configuration
    container_def = current_task_def['containerDefinitions'][0].copy()
    
    # Update secrets with correct format (use JSON key syntax)
    container_def['secrets'] = [
        {
            "name": "DATABASE_PASSWORD",
            "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB:password::"
        },
        {
            "name": "REDIS_PASSWORD",
            "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/redis-7UEzui:password::"
        }
    ]
    
    # Create new task definition
    new_task_def = {
        'family': current_task_def['family'],
        'taskRoleArn': current_task_def.get('taskRoleArn'),
        'executionRoleArn': current_task_def.get('executionRoleArn'),
        'networkMode': current_task_def['networkMode'],
        'requiresCompatibilities': current_task_def['requiresCompatibilities'],
        'cpu': str(NEW_CPU_UNITS),
        'memory': str(NEW_MEMORY_MB),
        'containerDefinitions': [container_def]
    }
    
    if 'ephemeralStorage' in current_task_def:
        new_task_def['ephemeralStorage'] = current_task_def['ephemeralStorage']
    
    # Register new task definition
    print(f"📝 Registering new task definition...")
    print(f"   Memory: {NEW_MEMORY_MB} MB (8GB)")
    print(f"   CPU: {NEW_CPU_UNITS} units")
    print(f"   Fixed secrets format")
    
    register_response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    
    print(f"✅ New task definition registered: {new_task_def_arn}")
    
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
        'task_definition_arn': new_task_def_arn,
        'memory_mb': NEW_MEMORY_MB,
        'cpu_units': NEW_CPU_UNITS,
        'secrets_fixed': True
    }
    
    results_file = f'8gb-deployment-fixed-secrets-{timestamp}.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📝 Results saved to: {results_file}")

if __name__ == "__main__":
    main()
