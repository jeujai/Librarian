#!/usr/bin/env python3
"""
Fix database environment variables to match what the application expects
"""

import boto3
import json

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
OLD_DB_ENDPOINT = 'ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com'

ecs = boto3.client('ecs', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

print("🔧 Fixing database environment variables...")

# Get current task definition
response = ecs.describe_services(
    cluster=CLUSTER_NAME,
    services=[SERVICE_NAME]
)

task_def_arn = response['services'][0]['taskDefinition']
task_def_response = ecs.describe_task_definition(taskDefinition=task_def_arn)
task_def = task_def_response['taskDefinition']

print(f"   Current task definition: {task_def_arn}")

# Update environment variables
container_def = task_def['containerDefinitions'][0]
env_vars = container_def.get('environment', [])

# Remove old POSTGRES_* variables
env_vars = [e for e in env_vars if not e['name'].startswith('POSTGRES_')]

# Add correct DB_* variables
db_env_vars = {
    'DB_HOST': OLD_DB_ENDPOINT,
    'DB_PORT': '5432',
    'DB_NAME': 'multimodal_librarian',
    'DB_USER': 'postgres'
}

for key, value in db_env_vars.items():
    # Remove if exists
    env_vars = [e for e in env_vars if e['name'] != key]
    # Add new value
    env_vars.append({'name': key, 'value': value})
    print(f"   ✓ Set {key}: {value}")

container_def['environment'] = env_vars

# Ensure DB_PASSWORD secret is set
secrets = container_def.get('secrets', [])
has_db_password = any(s['name'] == 'DB_PASSWORD' for s in secrets)

if not has_db_password:
    # Get the secret ARN
    secret_response = secretsmanager.describe_secret(SecretId='multimodal-librarian/learning/database')
    secret_arn = secret_response['ARN']
    
    secrets.append({
        'name': 'DB_PASSWORD',
        'valueFrom': f"{secret_arn}:password::"
    })
    print(f"   ✓ Added DB_PASSWORD secret reference")

container_def['secrets'] = secrets

# Remove fields that shouldn't be in registration
fields_to_remove = [
    'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
    'compatibilities', 'registeredAt', 'registeredBy'
]

for field in fields_to_remove:
    task_def.pop(field, None)

# Register new task definition
print("\n📝 Registering new task definition...")
response = ecs.register_task_definition(**task_def)
new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
print(f"   ✓ New task definition: {new_task_def_arn}")

# Update service
print("\n🚀 Updating ECS service...")
response = ecs.update_service(
    cluster=CLUSTER_NAME,
    service=SERVICE_NAME,
    taskDefinition=new_task_def_arn,
    forceNewDeployment=True,
    healthCheckGracePeriodSeconds=300
)

print(f"   ✓ Service update initiated")
print(f"\n✅ Done! Monitor deployment with:")
print(f"   python scripts/monitor-deployment-progress.py")
