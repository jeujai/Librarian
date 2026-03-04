#!/usr/bin/env python3
"""
Fix POSTGRES_PASSWORD Secret Reference

Updates the task definition to use the correct secret for POSTGRES_PASSWORD
instead of the deleted full-ml/database secret.
"""

import boto3
import json
from datetime import datetime

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TASK_FAMILY = 'multimodal-lib-prod-app'

# Correct secret ARN
CORRECT_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/learning/database-TSnLsl'

ecs = boto3.client('ecs', region_name=REGION)

def main():
    print("="*80)
    print("FIX POSTGRES_PASSWORD SECRET REFERENCE")
    print("="*80)
    
    # Get current task definition
    print("\n1. Fetching current task definition...")
    response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
    task_def = response['taskDefinition']
    
    print(f"   Current: {task_def['family']}:{task_def['revision']}")
    
    # Get container definition
    container_def = task_def['containerDefinitions'][0]
    
    # Show current secrets
    print("\n2. Current secrets configuration:")
    for secret in container_def.get('secrets', []):
        print(f"   {secret['name']}: {secret['valueFrom']}")
    
    # Update POSTGRES_PASSWORD secret
    print("\n3. Updating POSTGRES_PASSWORD secret...")
    updated_secrets = []
    for secret in container_def.get('secrets', []):
        if secret['name'] == 'POSTGRES_PASSWORD':
            # Update to use the correct secret with password field
            updated_secret = {
                'name': 'POSTGRES_PASSWORD',
                'valueFrom': f'{CORRECT_SECRET_ARN}:password::'
            }
            updated_secrets.append(updated_secret)
            print(f"   ✅ Updated POSTGRES_PASSWORD to: {updated_secret['valueFrom']}")
        else:
            updated_secrets.append(secret)
    
    # Create new task definition
    print("\n4. Creating new task definition...")
    
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def['taskRoleArn'],
        'executionRoleArn': task_def['executionRoleArn'],
        'networkMode': task_def['networkMode'],
        'containerDefinitions': [
            {
                **container_def,
                'secrets': updated_secrets
            }
        ],
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory']
    }
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_revision = response['taskDefinition']['revision']
    
    print(f"   ✅ Created: {task_def['family']}:{new_revision}")
    
    # Show updated secrets
    print("\n5. New secrets configuration:")
    for secret in response['taskDefinition']['containerDefinitions'][0]['secrets']:
        print(f"   {secret['name']}: {secret['valueFrom']}")
    
    # Update service
    print("\n6. Updating ECS service...")
    ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        taskDefinition=f"{task_def['family']}:{new_revision}",
        forceNewDeployment=True
    )
    
    print(f"   ✅ Service updated to use revision {new_revision}")
    
    print("\n" + "="*80)
    print("SUCCESS")
    print("="*80)
    print("\nThe task definition has been updated to use the correct secret.")
    print("New tasks will now be able to start successfully.")
    print("\nNext steps:")
    print("1. Wait 2-3 minutes for new tasks to start")
    print("2. Run: python3 scripts/verify-aws-database-connectivity.py")
    print("3. Check that tasks are running and healthy")
    
    # Save results
    timestamp = int(datetime.now().timestamp())
    result = {
        'timestamp': timestamp,
        'old_revision': task_def['revision'],
        'new_revision': new_revision,
        'updated_secret': {
            'name': 'POSTGRES_PASSWORD',
            'old_arn': 'arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB',
            'new_arn': f'{CORRECT_SECRET_ARN}:password::'
        }
    }
    
    with open(f'postgres-password-fix-{timestamp}.json', 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResults saved to: postgres-password-fix-{timestamp}.json")

if __name__ == '__main__':
    main()
