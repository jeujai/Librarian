#!/usr/bin/env python3
"""
Restore OpenSearch, Vector Store, and Neptune Graph Database for multimodal-lib-prod-service-alb

This script:
1. Gets the current task definition for multimodal-lib-prod-service-alb
2. Removes the SKIP_* environment variables that disable databases
3. Adds proper database connection environment variables
4. Registers a new task definition
5. Updates the ECS service to use the new task definition
"""

import boto3
import json
import sys
from datetime import datetime

# AWS clients
ecs = boto3.client('ecs')
neptune = boto3.client('neptune')
opensearch = boto3.client('opensearch')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TASK_FAMILY = 'multimodal-lib-prod-app'
NEPTUNE_CLUSTER_ID = 'multimodal-lib-prod-neptune'
OPENSEARCH_DOMAIN = 'multimodal-lib-prod-search'

def get_current_task_definition():
    """Get the current task definition"""
    print(f"📋 Getting current task definition for {TASK_FAMILY}...")
    
    response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
    task_def = response['taskDefinition']
    
    print(f"✅ Current task definition: {task_def['taskDefinitionArn']}")
    print(f"   Revision: {task_def['revision']}")
    
    return task_def

def get_database_endpoints():
    """Get Neptune and OpenSearch endpoints"""
    print("\n🔍 Getting database endpoints...")
    
    # Get Neptune endpoint
    neptune_response = neptune.describe_db_clusters(
        DBClusterIdentifier=NEPTUNE_CLUSTER_ID
    )
    neptune_endpoint = neptune_response['DBClusters'][0]['Endpoint']
    neptune_port = neptune_response['DBClusters'][0]['Port']
    
    print(f"✅ Neptune endpoint: {neptune_endpoint}:{neptune_port}")
    
    # Get OpenSearch endpoint
    opensearch_response = opensearch.describe_domain(
        DomainName=OPENSEARCH_DOMAIN
    )
    opensearch_endpoint = opensearch_response['DomainStatus']['Endpoints']['vpc']
    
    print(f"✅ OpenSearch endpoint: https://{opensearch_endpoint}")
    
    return {
        'neptune_endpoint': neptune_endpoint,
        'neptune_port': str(neptune_port),
        'opensearch_endpoint': f"https://{opensearch_endpoint}"
    }

def update_environment_variables(task_def, endpoints):
    """Update environment variables to enable databases"""
    print("\n🔧 Updating environment variables...")
    
    container_def = task_def['containerDefinitions'][0]
    env_vars = container_def.get('environment', [])
    
    # Remove SKIP_* variables
    skip_vars_to_remove = [
        'SKIP_OPENSEARCH_INIT',
        'SKIP_VECTOR_STORE_INIT',
        'SKIP_NEPTUNE_INIT',
        'SKIP_KNOWLEDGE_GRAPH_INIT'
    ]
    
    original_count = len(env_vars)
    env_vars = [var for var in env_vars if var['name'] not in skip_vars_to_remove]
    removed_count = original_count - len(env_vars)
    
    if removed_count > 0:
        print(f"   Removed {removed_count} SKIP_* variables")
    
    # Add/update database connection variables
    database_vars = {
        'NEPTUNE_ENDPOINT': endpoints['neptune_endpoint'],
        'NEPTUNE_PORT': endpoints['neptune_port'],
        'OPENSEARCH_ENDPOINT': endpoints['opensearch_endpoint'],
        'OPENSEARCH_HOST': endpoints['opensearch_endpoint'],
        'VECTOR_STORE_ENABLED': 'true',
        'KNOWLEDGE_GRAPH_ENABLED': 'true',
        'USE_AWS_OPENSEARCH': 'true',
        'USE_AWS_NEPTUNE': 'true'
    }
    
    # Update or add variables
    env_dict = {var['name']: var['value'] for var in env_vars}
    env_dict.update(database_vars)
    
    # Convert back to list format
    updated_env_vars = [{'name': k, 'value': v} for k, v in sorted(env_dict.items())]
    
    container_def['environment'] = updated_env_vars
    
    print(f"✅ Added/updated {len(database_vars)} database configuration variables")
    print(f"   Total environment variables: {len(updated_env_vars)}")
    
    return task_def

def register_new_task_definition(task_def):
    """Register a new task definition"""
    print("\n📝 Registering new task definition...")
    
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
    response = ecs.register_task_definition(**task_def)
    new_task_def = response['taskDefinition']
    
    print(f"✅ New task definition registered: {new_task_def['taskDefinitionArn']}")
    print(f"   Revision: {new_task_def['revision']}")
    
    return new_task_def

def update_service(task_def_arn):
    """Update the ECS service to use the new task definition"""
    print(f"\n🚀 Updating service {SERVICE_NAME}...")
    
    response = ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        taskDefinition=task_def_arn,
        forceNewDeployment=True
    )
    
    service = response['service']
    
    print(f"✅ Service updated successfully")
    print(f"   Service: {service['serviceName']}")
    print(f"   Status: {service['status']}")
    print(f"   Desired count: {service['desiredCount']}")
    print(f"   Task definition: {service['taskDefinition']}")
    
    return service

def wait_for_deployment():
    """Wait for the deployment to stabilize"""
    print("\n⏳ Waiting for deployment to stabilize...")
    print("   This may take several minutes...")
    
    waiter = ecs.get_waiter('services_stable')
    
    try:
        waiter.wait(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 40  # 10 minutes
            }
        )
        print("✅ Deployment stabilized successfully!")
        return True
    except Exception as e:
        print(f"⚠️  Deployment did not stabilize within timeout: {e}")
        print("   Check the ECS console for deployment status")
        return False

def verify_deployment():
    """Verify the deployment"""
    print("\n🔍 Verifying deployment...")
    
    response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = response['services'][0]
    
    print(f"   Service status: {service['status']}")
    print(f"   Running count: {service['runningCount']}/{service['desiredCount']}")
    
    # Check deployments
    deployments = service['deployments']
    print(f"\n   Active deployments: {len(deployments)}")
    
    for i, deployment in enumerate(deployments, 1):
        print(f"\n   Deployment {i}:")
        print(f"      Status: {deployment['status']}")
        print(f"      Desired: {deployment['desiredCount']}")
        print(f"      Running: {deployment['runningCount']}")
        print(f"      Task definition: {deployment['taskDefinition'].split('/')[-1]}")
    
    # Check tasks
    tasks_response = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        print(f"\n   Running tasks: {len(tasks_response['taskArns'])}")
        
        tasks_detail = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=tasks_response['taskArns']
        )
        
        for task in tasks_detail['tasks']:
            print(f"      Task: {task['taskArn'].split('/')[-1]}")
            print(f"         Status: {task['lastStatus']}")
            print(f"         Health: {task.get('healthStatus', 'UNKNOWN')}")
    
    return service

def main():
    """Main execution"""
    print("=" * 80)
    print("🔄 Restoring Databases for multimodal-lib-prod-service-alb")
    print("=" * 80)
    
    try:
        # Step 1: Get current task definition
        task_def = get_current_task_definition()
        
        # Step 2: Get database endpoints
        endpoints = get_database_endpoints()
        
        # Step 3: Update environment variables
        updated_task_def = update_environment_variables(task_def, endpoints)
        
        # Step 4: Register new task definition
        new_task_def = register_new_task_definition(updated_task_def)
        
        # Step 5: Update service
        service = update_service(new_task_def['taskDefinitionArn'])
        
        # Step 6: Wait for deployment
        wait_for_deployment()
        
        # Step 7: Verify deployment
        verify_deployment()
        
        print("\n" + "=" * 80)
        print("✅ Database restoration completed successfully!")
        print("=" * 80)
        print("\n📋 Summary:")
        print(f"   - Removed SKIP_* environment variables")
        print(f"   - Added Neptune endpoint: {endpoints['neptune_endpoint']}")
        print(f"   - Added OpenSearch endpoint: {endpoints['opensearch_endpoint']}")
        print(f"   - Enabled Vector Store and Knowledge Graph")
        print(f"   - Deployed new task definition: {new_task_def['family']}:{new_task_def['revision']}")
        
        print("\n🔍 Next steps:")
        print("   1. Monitor the service in ECS console")
        print("   2. Check CloudWatch logs for any initialization errors")
        print("   3. Verify database connectivity from the application")
        print("   4. Test Vector Store and Knowledge Graph functionality")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
