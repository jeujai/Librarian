#!/usr/bin/env python3
"""
Update ECS Task Definition with New PostgreSQL Endpoint

Updates the ECS task definition to use the new PostgreSQL database
endpoint in the ECS VPC.
"""

import boto3
import json
from datetime import datetime

# Configuration
NEW_POSTGRES_HOST = "ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com"
NEW_POSTGRES_PORT = "5432"
ECS_CLUSTER = "multimodal-lib-prod-cluster"
ECS_SERVICE = "multimodal-lib-prod-service-alb"

# AWS clients
ecs = boto3.client('ecs')

def get_current_task_definition():
    """Get the current task definition from the service."""
    print(f"\n=== Getting current task definition ===")
    
    # Get service details
    response = ecs.describe_services(
        cluster=ECS_CLUSTER,
        services=[ECS_SERVICE]
    )
    
    if not response['services']:
        raise Exception(f"Service {ECS_SERVICE} not found in cluster {ECS_CLUSTER}")
    
    service = response['services'][0]
    task_def_arn = service['taskDefinition']
    
    print(f"  Current task definition: {task_def_arn}")
    
    # Get task definition details
    response = ecs.describe_task_definition(
        taskDefinition=task_def_arn
    )
    
    return response['taskDefinition']

def update_environment_variables(task_def):
    """Update POSTGRES_HOST and POSTGRES_PORT in task definition."""
    print(f"\n=== Updating environment variables ===")
    
    container_def = task_def['containerDefinitions'][0]
    env_vars = container_def.get('environment', [])
    
    # Track changes
    updated_host = False
    updated_port = False
    
    # Update existing variables
    for env_var in env_vars:
        if env_var['name'] == 'POSTGRES_HOST':
            old_value = env_var['value']
            env_var['value'] = NEW_POSTGRES_HOST
            print(f"  Updated POSTGRES_HOST:")
            print(f"    Old: {old_value}")
            print(f"    New: {NEW_POSTGRES_HOST}")
            updated_host = True
        elif env_var['name'] == 'POSTGRES_PORT':
            old_value = env_var['value']
            env_var['value'] = NEW_POSTGRES_PORT
            print(f"  Updated POSTGRES_PORT:")
            print(f"    Old: {old_value}")
            print(f"    New: {NEW_POSTGRES_PORT}")
            updated_port = True
    
    # Add variables if they don't exist
    if not updated_host:
        env_vars.append({'name': 'POSTGRES_HOST', 'value': NEW_POSTGRES_HOST})
        print(f"  Added POSTGRES_HOST: {NEW_POSTGRES_HOST}")
    
    if not updated_port:
        env_vars.append({'name': 'POSTGRES_PORT', 'value': NEW_POSTGRES_PORT})
        print(f"  Added POSTGRES_PORT: {NEW_POSTGRES_PORT}")
    
    container_def['environment'] = env_vars
    return task_def

def register_new_task_definition(task_def):
    """Register a new task definition revision."""
    print(f"\n=== Registering new task definition ===")
    
    # Remove fields that can't be used in registration
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
    
    # Register new revision
    response = ecs.register_task_definition(**task_def)
    
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    new_revision = response['taskDefinition']['revision']
    
    print(f"  ✓ New task definition registered")
    print(f"    ARN: {new_task_def_arn}")
    print(f"    Revision: {new_revision}")
    
    return new_task_def_arn

def update_service(new_task_def_arn):
    """Update the ECS service to use the new task definition."""
    print(f"\n=== Updating ECS service ===")
    
    response = ecs.update_service(
        cluster=ECS_CLUSTER,
        service=ECS_SERVICE,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"  ✓ Service update initiated")
    print(f"    Service: {ECS_SERVICE}")
    print(f"    Task Definition: {new_task_def_arn}")
    print(f"    Deployment Status: {response['service']['deployments'][0]['status']}")
    
    return response

def print_summary():
    """Print update summary and next steps."""
    print("\n" + "="*70)
    print("ECS TASK DEFINITION UPDATE SUMMARY")
    print("="*70)
    
    print(f"\n✓ ECS task definition updated with new PostgreSQL endpoint!")
    
    print(f"\nUpdated Environment Variables:")
    print(f"  POSTGRES_HOST={NEW_POSTGRES_HOST}")
    print(f"  POSTGRES_PORT={NEW_POSTGRES_PORT}")
    
    print(f"\nNext Steps:")
    print(f"  1. Monitor deployment progress:")
    print(f"     aws ecs describe-services \\")
    print(f"       --cluster {ECS_CLUSTER} \\")
    print(f"       --services {ECS_SERVICE}")
    
    print(f"\n  2. Check task logs for database connectivity:")
    print(f"     aws logs tail /ecs/multimodal-librarian --follow")
    
    print(f"\n  3. Test application endpoints to verify database access")
    
    print(f"\n  4. Once verified, delete old database:")
    print(f"     aws rds delete-db-instance \\")
    print(f"       --db-instance-identifier multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro \\")
    print(f"       --skip-final-snapshot")
    
    print("\n" + "="*70)

def main():
    """Main update workflow."""
    print("="*70)
    print("Update ECS Task Definition with New PostgreSQL Endpoint")
    print("="*70)
    
    print(f"\nThis will update the ECS service to use:")
    print(f"  POSTGRES_HOST: {NEW_POSTGRES_HOST}")
    print(f"  POSTGRES_PORT: {NEW_POSTGRES_PORT}")
    
    response = input("\nProceed with update? (yes/no): ")
    if response.lower() != 'yes':
        print("Update cancelled")
        return
    
    try:
        # Get current task definition
        task_def = get_current_task_definition()
        
        # Update environment variables
        updated_task_def = update_environment_variables(task_def)
        
        # Register new task definition
        new_task_def_arn = register_new_task_definition(updated_task_def)
        
        # Update service
        update_service(new_task_def_arn)
        
        # Print summary
        print_summary()
        
        # Save update details
        update_details = {
            'timestamp': datetime.utcnow().isoformat(),
            'cluster': ECS_CLUSTER,
            'service': ECS_SERVICE,
            'new_task_definition': new_task_def_arn,
            'postgres_host': NEW_POSTGRES_HOST,
            'postgres_port': NEW_POSTGRES_PORT
        }
        
        filename = f"ecs-postgres-update-{int(datetime.now().timestamp())}.json"
        with open(filename, 'w') as f:
            json.dump(update_details, f, indent=2)
        
        print(f"\nUpdate details saved to: {filename}")
        
    except Exception as e:
        print(f"\n✗ Update failed: {e}")
        print("\nPlease review the error and try again")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
