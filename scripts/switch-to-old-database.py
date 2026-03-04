#!/usr/bin/env python3
"""
Switch ECS service back to the old PostgreSQL database (ml-librarian-postgres-prod)
which is in the same VPC as the ECS service.
"""

import boto3
import json
import time
from datetime import datetime

# Configuration
REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
OLD_DB_ENDPOINT = 'ml-librarian-postgres-prod.cq1iiac2gfkf.us-east-1.rds.amazonaws.com'
SECRET_NAME = 'multimodal-librarian/learning/database'

# Initialize AWS clients
ecs = boto3.client('ecs', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

def get_current_task_definition():
    """Get the current task definition from the service"""
    print("📋 Getting current task definition...")
    
    response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not response['services']:
        raise Exception(f"Service {SERVICE_NAME} not found")
    
    task_def_arn = response['services'][0]['taskDefinition']
    print(f"   Current task definition: {task_def_arn}")
    
    # Get full task definition
    task_def_response = ecs.describe_task_definition(taskDefinition=task_def_arn)
    return task_def_response['taskDefinition']

def update_database_config(task_def):
    """Update the task definition with old database endpoint"""
    print(f"\n🔄 Updating database configuration...")
    print(f"   Old endpoint: {OLD_DB_ENDPOINT}")
    print(f"   Using DB_* environment variables (required by connection.py)")
    
    # Update environment variables
    container_def = task_def['containerDefinitions'][0]
    
    # Find and update DB_HOST
    env_vars = container_def.get('environment', [])
    updated = False
    
    for env in env_vars:
        if env['name'] == 'DB_HOST':
            old_value = env['value']
            env['value'] = OLD_DB_ENDPOINT
            print(f"   ✓ Updated DB_HOST")
            print(f"     From: {old_value}")
            print(f"     To:   {OLD_DB_ENDPOINT}")
            updated = True
            break
    
    if not updated:
        # Add if not exists
        env_vars.append({
            'name': 'DB_HOST',
            'value': OLD_DB_ENDPOINT
        })
        print(f"   ✓ Added DB_HOST: {OLD_DB_ENDPOINT}")
    
    # Ensure we have the secret reference for password
    secrets = container_def.get('secrets', [])
    has_password_secret = any(s['name'] == 'DB_PASSWORD' for s in secrets)
    
    if not has_password_secret:
        # Get the secret ARN
        secret_response = secretsmanager.describe_secret(SecretId=SECRET_NAME)
        secret_arn = secret_response['ARN']
        
        secrets.append({
            'name': 'DB_PASSWORD',
            'valueFrom': f"{secret_arn}:password::"
        })
        print(f"   ✓ Added DB_PASSWORD secret reference")
    
    # Ensure other database env vars are set (using DB_* naming convention)
    db_env_vars = {
        'DB_USER': 'postgres',
        'DB_NAME': 'multimodal_librarian',
        'DB_PORT': '5432'
    }
    
    for key, value in db_env_vars.items():
        if not any(e['name'] == key for e in env_vars):
            env_vars.append({'name': key, 'value': value})
            print(f"   ✓ Added {key}: {value}")
    
    container_def['environment'] = env_vars
    container_def['secrets'] = secrets
    
    return task_def

def register_new_task_definition(task_def):
    """Register a new task definition"""
    print("\n📝 Registering new task definition...")
    
    # Remove fields that shouldn't be in registration
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'compatibilities', 'registeredAt', 'registeredBy'
    ]
    
    for field in fields_to_remove:
        task_def.pop(field, None)
    
    response = ecs.register_task_definition(**task_def)
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    
    print(f"   ✓ New task definition: {new_task_def_arn}")
    return new_task_def_arn

def update_service(new_task_def_arn):
    """Update the ECS service with the new task definition"""
    print("\n🚀 Updating ECS service...")
    
    response = ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"   ✓ Service update initiated")
    return response

def wait_for_deployment():
    """Wait for the deployment to complete"""
    print("\n⏳ Waiting for deployment to complete...")
    print("   This may take several minutes...")
    
    max_wait = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = response['services'][0]
        deployments = service['deployments']
        
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            running_count = deployments[0]['runningCount']
            desired_count = deployments[0]['desiredCount']
            
            print(f"   Running: {running_count}/{desired_count}")
            
            if running_count == desired_count:
                print("\n✅ Deployment completed successfully!")
                return True
        
        time.sleep(10)
    
    print("\n⚠️  Deployment is taking longer than expected")
    print("   Check the ECS console for details")
    return False

def verify_database_connection():
    """Verify the database configuration"""
    print("\n🔍 Verifying database configuration...")
    
    # Get the old database details
    rds = boto3.client('rds', region_name=REGION)
    db_response = rds.describe_db_instances(
        DBInstanceIdentifier='ml-librarian-postgres-prod'
    )
    
    db_instance = db_response['DBInstances'][0]
    vpc_id = db_instance['DBSubnetGroup']['VpcId']
    
    print(f"   Database VPC: {vpc_id}")
    print(f"   Database Endpoint: {db_instance['Endpoint']['Address']}")
    print(f"   Database Status: {db_instance['DBInstanceStatus']}")
    
    # Get ECS service VPC
    response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = response['services'][0]
    subnet_ids = service['networkConfiguration']['awsvpcConfiguration']['subnets']
    
    ec2 = boto3.client('ec2', region_name=REGION)
    subnet_response = ec2.describe_subnets(SubnetIds=[subnet_ids[0]])
    ecs_vpc_id = subnet_response['Subnets'][0]['VpcId']
    
    print(f"   ECS Service VPC: {ecs_vpc_id}")
    
    if vpc_id == ecs_vpc_id:
        print("   ✅ Database and ECS service are in the SAME VPC!")
    else:
        print("   ⚠️  WARNING: Database and ECS service are in DIFFERENT VPCs")
        print("   This may cause connectivity issues")

def main():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'database-switch-{timestamp}.json'
    
    print("=" * 70)
    print("🔄 SWITCHING TO OLD DATABASE (ml-librarian-postgres-prod)")
    print("=" * 70)
    
    try:
        # Verify database configuration first
        verify_database_connection()
        
        # Get current task definition
        task_def = get_current_task_definition()
        
        # Update database configuration
        updated_task_def = update_database_config(task_def)
        
        # Register new task definition
        new_task_def_arn = register_new_task_definition(updated_task_def)
        
        # Update service
        update_response = update_service(new_task_def_arn)
        
        # Save results
        results = {
            'timestamp': timestamp,
            'old_database': OLD_DB_ENDPOINT,
            'new_task_definition': new_task_def_arn,
            'service_update': {
                'cluster': CLUSTER_NAME,
                'service': SERVICE_NAME,
                'status': 'initiated'
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {output_file}")
        
        # Wait for deployment
        success = wait_for_deployment()
        
        if success:
            print("\n" + "=" * 70)
            print("✅ DATABASE SWITCH COMPLETED SUCCESSFULLY!")
            print("=" * 70)
            print(f"\n📊 Summary:")
            print(f"   • Database: {OLD_DB_ENDPOINT}")
            print(f"   • Task Definition: {new_task_def_arn}")
            print(f"   • Service: {SERVICE_NAME}")
            print(f"\n🔗 Next steps:")
            print(f"   1. Test the application health endpoint")
            print(f"   2. Verify database connectivity")
            print(f"   3. Check application logs")
        else:
            print("\n⚠️  Deployment status unclear - please check ECS console")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
