#!/usr/bin/env python3
"""
Fix Database Credentials Mismatch

This script fixes the mismatch between POSTGRES_HOST and POSTGRES_PASSWORD
by updating the task definition to use the correct database host that matches
the password in Secrets Manager.
"""

import boto3
import json
import sys
from datetime import datetime

def main():
    region = 'us-east-1'
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    ecs = boto3.client('ecs', region_name=region)
    secretsmanager = boto3.client('secretsmanager', region_name=region)
    
    print("=" * 80)
    print("DATABASE CREDENTIALS MISMATCH FIX")
    print("=" * 80)
    
    # Get current service
    print("\n1. Getting current service configuration...")
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"ERROR: Service {service_name} not found!")
        return 1
    
    service = service_response['services'][0]
    current_task_def_arn = service['taskDefinition']
    print(f"   Current task definition: {current_task_def_arn}")
    
    # Get current task definition
    print("\n2. Getting current task definition...")
    task_def_response = ecs.describe_task_definition(
        taskDefinition=current_task_def_arn
    )
    task_def = task_def_response['taskDefinition']
    
    # Get the secret value to find the correct database host
    print("\n3. Checking Secrets Manager for database credentials...")
    secret_response = secretsmanager.get_secret_value(
        SecretId='multimodal-librarian/full-ml/database'
    )
    secret_data = json.loads(secret_response['SecretString'])
    correct_host = secret_data['host']
    correct_user = secret_data['username']
    correct_db = secret_data['dbname']
    
    print(f"   Secret contains credentials for: {correct_host}")
    print(f"   Username: {correct_user}")
    print(f"   Database: {correct_db}")
    
    # Check current environment variables
    container_def = task_def['containerDefinitions'][0]
    current_env = {env['name']: env['value'] for env in container_def.get('environment', [])}
    
    print(f"\n4. Current POSTGRES_HOST: {current_env.get('POSTGRES_HOST', 'NOT SET')}")
    print(f"   Current POSTGRES_USER: {current_env.get('POSTGRES_USER', 'NOT SET')}")
    print(f"   Current POSTGRES_DB: {current_env.get('POSTGRES_DB', 'NOT SET')}")
    
    if current_env.get('POSTGRES_HOST') == correct_host:
        print("\n✓ POSTGRES_HOST already matches the secret! No update needed.")
        return 0
    
    print(f"\n5. Updating POSTGRES_HOST to match secret...")
    print(f"   Old: {current_env.get('POSTGRES_HOST')}")
    print(f"   New: {correct_host}")
    
    # Update environment variables
    new_environment = []
    for env in container_def.get('environment', []):
        if env['name'] == 'POSTGRES_HOST':
            new_environment.append({'name': 'POSTGRES_HOST', 'value': correct_host})
        elif env['name'] == 'POSTGRES_USER':
            new_environment.append({'name': 'POSTGRES_USER', 'value': correct_user})
        elif env['name'] == 'POSTGRES_DB':
            new_environment.append({'name': 'POSTGRES_DB', 'value': correct_db})
        else:
            new_environment.append(env)
    
    container_def['environment'] = new_environment
    
    # Register new task definition
    print("\n6. Registering new task definition...")
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def['networkMode'],
        'containerDefinitions': [container_def],
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory'],
    }
    
    if 'volumes' in task_def:
        new_task_def['volumes'] = task_def['volumes']
    
    register_response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    new_revision = register_response['taskDefinition']['revision']
    
    print(f"   ✓ New task definition registered: {task_def['family']}:{new_revision}")
    
    # Update service
    print("\n7. Updating service with new task definition...")
    update_response = ecs.update_service(
        cluster=cluster_name,
        service=service_name,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"   ✓ Service updated successfully!")
    print(f"   Deployment ID: {update_response['service']['deployments'][0]['id']}")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f'database-credentials-fix-{timestamp}.json'
    
    result = {
        'timestamp': timestamp,
        'old_host': current_env.get('POSTGRES_HOST'),
        'new_host': correct_host,
        'old_task_definition': current_task_def_arn,
        'new_task_definition': new_task_def_arn,
        'service': service_name,
        'cluster': cluster_name,
        'deployment_id': update_response['service']['deployments'][0]['id']
    }
    
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n8. Results saved to: {result_file}")
    
    print("\n" + "=" * 80)
    print("DATABASE CREDENTIALS FIX COMPLETE")
    print("=" * 80)
    print("\nThe service will now redeploy with the correct database host.")
    print("Monitor the deployment with:")
    print(f"  aws ecs describe-services --cluster {cluster_name} --services {service_name} --region {region}")
    print("\nCheck logs with:")
    print(f"  aws logs tail /ecs/multimodal-lib-prod-app --follow --region {region}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
