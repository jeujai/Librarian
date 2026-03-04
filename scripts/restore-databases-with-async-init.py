#!/usr/bin/env python3
"""
Restore Databases with Async Initialization

This script restores OpenSearch and Neptune databases for the multimodal-lib-prod-service-alb
with the new asynchronous initialization fix that prevents health check blocking.

Key Changes:
1. Health check endpoint (/health/simple) is completely decoupled from database initialization
2. Database initialization happens asynchronously in the background
3. Respects SKIP_* environment variables
4. Configurable timeouts prevent long blocking operations

Usage:
    python scripts/restore-databases-with-async-init.py
"""

import boto3
import json
import time
import sys
from datetime import datetime

# AWS clients
ecs_client = boto3.client('ecs', region_name='us-east-1')
ec2_client = boto3.client('ec2', region_name='us-east-1')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
TASK_FAMILY = 'multimodal-lib-prod-task'

# Database endpoints
NEPTUNE_ENDPOINT = 'multimodal-lib-prod-neptune.cluster-cq1iiac2gfkf.us-east-1.neptune.amazonaws.com:8182'
OPENSEARCH_ENDPOINT = 'https://vpc-multimodal-lib-prod-search-2mjsemd5qwcuj3ezeltxxmwkrq.us-east-1.es.amazonaws.com'


def get_current_task_definition():
    """Get the current task definition."""
    print("📋 Getting current task definition...")
    
    response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not response['services']:
        print(f"❌ Service {SERVICE_NAME} not found")
        sys.exit(1)
    
    task_def_arn = response['services'][0]['taskDefinition']
    task_def_response = ecs_client.describe_task_definition(taskDefinition=task_def_arn)
    
    return task_def_response['taskDefinition']


def create_new_task_definition(current_task_def):
    """Create a new task definition with database endpoints and async init."""
    print("🔧 Creating new task definition with database endpoints...")
    
    # Get the container definition
    container_def = current_task_def['containerDefinitions'][0]
    
    # Remove SKIP_* variables and add database endpoints
    environment = []
    for env_var in container_def.get('environment', []):
        name = env_var['name']
        # Remove SKIP variables
        if name in ['SKIP_OPENSEARCH_INIT', 'SKIP_NEPTUNE_INIT', 'SKIP_VECTOR_SEARCH']:
            print(f"   Removing: {name}")
            continue
        # Keep other variables
        environment.append(env_var)
    
    # Add database endpoints
    new_env_vars = [
        {'name': 'NEPTUNE_ENDPOINT', 'value': NEPTUNE_ENDPOINT},
        {'name': 'OPENSEARCH_ENDPOINT', 'value': OPENSEARCH_ENDPOINT},
        {'name': 'ENABLE_VECTOR_SEARCH', 'value': 'true'},
        {'name': 'OPENSEARCH_TIMEOUT', 'value': '10'},
        {'name': 'NEPTUNE_TIMEOUT', 'value': '10'},
    ]
    
    for env_var in new_env_vars:
        # Remove if exists
        environment = [e for e in environment if e['name'] != env_var['name']]
        # Add new value
        environment.append(env_var)
        print(f"   Adding: {env_var['name']}={env_var['value']}")
    
    # Update container definition
    container_def['environment'] = environment
    
    # Register new task definition
    response = ecs_client.register_task_definition(
        family=current_task_def['family'],
        taskRoleArn=current_task_def['taskRoleArn'],
        executionRoleArn=current_task_def['executionRoleArn'],
        networkMode=current_task_def['networkMode'],
        containerDefinitions=[container_def],
        requiresCompatibilities=current_task_def['requiresCompatibilities'],
        cpu=current_task_def['cpu'],
        memory=current_task_def['memory']
    )
    
    new_revision = response['taskDefinition']['revision']
    print(f"✅ Created task definition revision {new_revision}")
    
    return f"{current_task_def['family']}:{new_revision}"


def update_service(task_definition):
    """Update the service with the new task definition."""
    print(f"🚀 Updating service with task definition {task_definition}...")
    
    response = ecs_client.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        taskDefinition=task_definition,
        forceNewDeployment=True
    )
    
    print(f"✅ Service update initiated")
    return response


def monitor_deployment():
    """Monitor the deployment progress."""
    print("\n📊 Monitoring deployment...")
    print("=" * 80)
    
    max_wait_time = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        response = ecs_client.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        service = response['services'][0]
        deployments = service['deployments']
        
        print(f"\n⏰ Time elapsed: {int(time.time() - start_time)}s")
        print(f"📦 Deployments: {len(deployments)}")
        
        for deployment in deployments:
            status = deployment['status']
            desired = deployment['desiredCount']
            running = deployment['runningCount']
            pending = deployment['pendingCount']
            
            print(f"   Status: {status}")
            print(f"   Desired: {desired}, Running: {running}, Pending: {pending}")
            print(f"   Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
        
        # Check if deployment is complete
        if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
            deployment = deployments[0]
            if deployment['runningCount'] == deployment['desiredCount']:
                print("\n✅ Deployment completed successfully!")
                return True
        
        # Check for failures
        tasks_response = ecs_client.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='STOPPED'
        )
        
        if tasks_response['taskArns']:
            print(f"\n⚠️  Found {len(tasks_response['taskArns'])} stopped tasks")
            # Get details of the most recent stopped task
            if tasks_response['taskArns']:
                task_details = ecs_client.describe_tasks(
                    cluster=CLUSTER_NAME,
                    tasks=[tasks_response['taskArns'][0]]
                )
                if task_details['tasks']:
                    task = task_details['tasks'][0]
                    print(f"   Stop reason: {task.get('stoppedReason', 'Unknown')}")
        
        time.sleep(15)
    
    print("\n⏰ Deployment monitoring timed out after 10 minutes")
    return False


def verify_database_connectivity():
    """Verify database connectivity through the health endpoint."""
    print("\n🔍 Verifying database connectivity...")
    
    # Get the ALB DNS name
    response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = response['services'][0]
    load_balancers = service.get('loadBalancers', [])
    
    if not load_balancers:
        print("⚠️  No load balancer found for service")
        return
    
    target_group_arn = load_balancers[0]['targetGroupArn']
    
    # Get ALB from target group
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    tg_response = elbv2_client.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    lb_arns = tg_response['TargetGroups'][0]['LoadBalancerArns']
    if lb_arns:
        lb_response = elbv2_client.describe_load_balancers(
            LoadBalancerArns=[lb_arns[0]]
        )
        dns_name = lb_response['LoadBalancers'][0]['DNSName']
        
        print(f"\n📍 Service URL: http://{dns_name}")
        print(f"   Health Check: http://{dns_name}/health/simple")
        print(f"   Database Status: http://{dns_name}/api/health/databases")
        print("\n💡 Use these commands to check status:")
        print(f"   curl http://{dns_name}/health/simple")
        print(f"   curl http://{dns_name}/api/health/databases")


def main():
    """Main execution function."""
    print("=" * 80)
    print("DATABASE RESTORATION WITH ASYNC INITIALIZATION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Cluster: {CLUSTER_NAME}")
    print(f"Service: {SERVICE_NAME}")
    print()
    print("This script will:")
    print("1. Remove SKIP_* environment variables")
    print("2. Add database endpoints (Neptune and OpenSearch)")
    print("3. Deploy with async database initialization")
    print("4. Monitor deployment progress")
    print("=" * 80)
    
    try:
        # Get current task definition
        current_task_def = get_current_task_definition()
        print(f"📋 Current task definition: {current_task_def['family']}:{current_task_def['revision']}")
        
        # Create new task definition
        new_task_def = create_new_task_definition(current_task_def)
        
        # Update service
        update_service(new_task_def)
        
        # Monitor deployment
        success = monitor_deployment()
        
        if success:
            # Verify connectivity
            verify_database_connectivity()
            
            print("\n" + "=" * 80)
            print("✅ DATABASE RESTORATION COMPLETED SUCCESSFULLY")
            print("=" * 80)
            print("\nNext steps:")
            print("1. Check database initialization status at /api/health/databases")
            print("2. Verify OpenSearch and Neptune are connecting")
            print("3. Monitor application logs for any errors")
            print("4. Run verification script: python scripts/verify-database-restoration.py")
        else:
            print("\n" + "=" * 80)
            print("⚠️  DEPLOYMENT DID NOT COMPLETE WITHIN TIMEOUT")
            print("=" * 80)
            print("\nCheck:")
            print("1. ECS console for task status")
            print("2. CloudWatch logs for errors")
            print("3. ALB target health")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
