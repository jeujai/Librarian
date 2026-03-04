#!/usr/bin/env python3
"""
Fix PostgreSQL Environment Variables in Task Definition

This script fixes the environment variable names to match what the Settings class expects.
The Settings class (in config/config.py) expects POSTGRES_* variables, not DB_* variables.

Root Cause:
- Task definition: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
- Settings class expects: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

This mismatch causes the Settings class to use default values (localhost:5432), which
causes health checks to timeout and fail.
"""

import boto3
import json
import sys
from datetime import datetime

def fix_environment_variables():
    """Fix environment variable names in task definition."""
    
    ecs = boto3.client('ecs')
    
    print("=" * 80)
    print("FIX POSTGRESQL ENVIRONMENT VARIABLES")
    print("=" * 80)
    print()
    
    # Get current task definition
    print("📋 Getting current task definition...")
    response = ecs.describe_task_definition(
        taskDefinition='multimodal-lib-prod-app:47'
    )
    
    task_def = response['taskDefinition']
    container_def = task_def['containerDefinitions'][0]
    
    print(f"✅ Current task definition: {task_def['family']}:{task_def['revision']}")
    print()
    
    # Get current environment variables
    current_env = {env['name']: env['value'] for env in container_def.get('environment', [])}
    
    print("📊 Current environment variables:")
    for key in ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER']:
        value = current_env.get(key, 'NOT SET')
        print(f"  {key}: {value}")
    print()
    
    # Create mapping of old names to new names
    env_mapping = {
        'DB_HOST': 'POSTGRES_HOST',
        'DB_PORT': 'POSTGRES_PORT',
        'DB_NAME': 'POSTGRES_DB',
        'DB_USER': 'POSTGRES_USER',
    }
    
    # Update environment variables
    new_env = []
    renamed_vars = []
    
    for env_var in container_def.get('environment', []):
        name = env_var['name']
        value = env_var['value']
        
        if name in env_mapping:
            new_name = env_mapping[name]
            new_env.append({'name': new_name, 'value': value})
            renamed_vars.append(f"{name} → {new_name}")
            print(f"🔄 Renaming: {name} → {new_name}")
        else:
            new_env.append(env_var)
    
    print()
    print(f"✅ Renamed {len(renamed_vars)} environment variables")
    print()
    
    # Update secrets (DB_PASSWORD → POSTGRES_PASSWORD)
    new_secrets = []
    for secret in container_def.get('secrets', []):
        name = secret['name']
        value_from = secret['valueFrom']
        
        if name == 'DB_PASSWORD':
            new_secrets.append({'name': 'POSTGRES_PASSWORD', 'valueFrom': value_from})
            print(f"🔄 Renaming secret: DB_PASSWORD → POSTGRES_PASSWORD")
        else:
            new_secrets.append(secret)
    
    print()
    
    # Create new task definition
    print("📝 Creating new task definition...")
    
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def['taskRoleArn'],
        'executionRoleArn': task_def['executionRoleArn'],
        'networkMode': task_def['networkMode'],
        'containerDefinitions': [
            {
                **container_def,
                'environment': new_env,
                'secrets': new_secrets
            }
        ],
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory']
    }
    
    # Remove fields that shouldn't be in register request
    for field in ['taskDefinitionArn', 'revision', 'status', 'registeredAt', 'registeredBy', 'compatibilities']:
        new_task_def.pop(field, None)
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_revision = response['taskDefinition']['revision']
    
    print(f"✅ New task definition registered: {task_def['family']}:{new_revision}")
    print()
    
    # Update service to use new task definition
    print("🔄 Updating ECS service...")
    
    ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=f"{task_def['family']}:{new_revision}",
        forceNewDeployment=True
    )
    
    print("✅ Service updated with new task definition")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("✅ Environment variables fixed:")
    for rename in renamed_vars:
        print(f"  • {rename}")
    print(f"  • DB_PASSWORD → POSTGRES_PASSWORD (secret)")
    print()
    print(f"✅ New task definition: {task_def['family']}:{new_revision}")
    print("✅ Service deployment started")
    print()
    print("🔍 Next steps:")
    print("  1. Monitor deployment: aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    print("  2. Check task logs for database connection success")
    print("  3. Test health endpoint: curl http://<task-ip>:8000/api/health/simple")
    print("  4. Verify ALB target health")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'old_task_definition': f"{task_def['family']}:{task_def['revision']}",
        'new_task_definition': f"{task_def['family']}:{new_revision}",
        'renamed_variables': renamed_vars,
        'cluster': 'multimodal-lib-prod-cluster',
        'service': 'multimodal-lib-prod-service'
    }
    
    filename = f"postgres-env-fix-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"📄 Results saved to: {filename}")
    print()
    
    return results

if __name__ == '__main__':
    try:
        results = fix_environment_variables()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
