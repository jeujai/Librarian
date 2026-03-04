#!/usr/bin/env python3
"""
Fix Health Check Command

This script updates the ECS task definition to use Python's urllib instead of curl
for the health check, which is guaranteed to be available in the container.
"""

import boto3
import json
import time
from datetime import datetime

def fix_health_check_command():
    """Update the health check command to use Python instead of curl."""
    
    print("="*80)
    print("FIXING HEALTH CHECK COMMAND")
    print("="*80)
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # Get current task definition
    print("\n📋 Getting current task definition...")
    response = ecs.describe_task_definition(
        taskDefinition='multimodal-lib-prod-app'
    )
    
    current_task_def = response['taskDefinition']
    current_revision = current_task_def['revision']
    
    print(f"   Current revision: {current_revision}")
    print(f"   Current health check: {current_task_def['containerDefinitions'][0].get('healthCheck', {}).get('command', 'None')}")
    
    # Create new task definition with Python-based health check
    print("\n🔧 Creating new task definition with Python-based health check...")
    
    # Remove fields that can't be in register_task_definition
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'compatibilities', 'registeredAt', 'registeredBy'
    ]
    
    new_task_def = {k: v for k, v in current_task_def.items() if k not in fields_to_remove}
    
    # Update health check command to use Python
    # This is guaranteed to work since Python is the base image
    new_health_check = {
        'command': [
            'CMD-SHELL',
            'python -c "import urllib.request; import sys; urllib.request.urlopen(\'http://localhost:8000/api/health/minimal\', timeout=10); sys.exit(0)" || exit 1'
        ],
        'interval': 30,
        'timeout': 15,
        'retries': 5,
        'startPeriod': 300
    }
    
    new_task_def['containerDefinitions'][0]['healthCheck'] = new_health_check
    
    # Register new task definition
    print(f"\n📝 Registering new task definition...")
    register_response = ecs.register_task_definition(**new_task_def)
    
    new_revision = register_response['taskDefinition']['revision']
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    
    print(f"   ✅ New revision created: {new_revision}")
    print(f"   Task definition ARN: {new_task_def_arn}")
    print(f"   New health check command: {new_health_check['command']}")
    
    # Update service to use new task definition
    print(f"\n🚀 Updating service to use new task definition...")
    
    update_response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=f'multimodal-lib-prod-app:{new_revision}',
        forceNewDeployment=True
    )
    
    print(f"   ✅ Service update initiated")
    print(f"   Deployment ID: {update_response['service']['deployments'][0]['id']}")
    
    # Monitor deployment
    print(f"\n⏳ Monitoring deployment progress...")
    print(f"   This will take a few minutes...")
    
    deployment_complete = False
    start_time = time.time()
    timeout = 600  # 10 minutes
    
    while not deployment_complete and (time.time() - start_time) < timeout:
        time.sleep(15)
        
        service_response = ecs.describe_services(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service']
        )
        
        service = service_response['services'][0]
        deployments = service['deployments']
        
        # Check if new deployment is primary and stable
        for deployment in deployments:
            if deployment['taskDefinition'].endswith(f':{new_revision}'):
                status = deployment['status']
                desired = deployment['desiredCount']
                running = deployment['runningCount']
                
                elapsed = int(time.time() - start_time)
                print(f"   [{elapsed}s] Status: {status}, Running: {running}/{desired}")
                
                if status == 'PRIMARY' and running == desired:
                    deployment_complete = True
                    break
    
    if deployment_complete:
        print(f"\n✅ Deployment completed successfully!")
        print(f"   Time taken: {int(time.time() - start_time)} seconds")
        
        # Wait a bit for health checks to run
        print(f"\n⏳ Waiting 60 seconds for health checks to run...")
        time.sleep(60)
        
        # Check task health status
        print(f"\n🏥 Checking task health status...")
        
        tasks_response = ecs.list_tasks(
            cluster='multimodal-lib-prod-cluster',
            serviceName='multimodal-lib-prod-service',
            desiredStatus='RUNNING'
        )
        
        if tasks_response['taskArns']:
            task_details = ecs.describe_tasks(
                cluster='multimodal-lib-prod-cluster',
                tasks=tasks_response['taskArns']
            )
            
            for task in task_details['tasks']:
                health_status = task.get('healthStatus', 'UNKNOWN')
                last_status = task['lastStatus']
                
                print(f"   Task: {task['taskArn'].split('/')[-1]}")
                print(f"   Status: {last_status}")
                print(f"   Health: {health_status}")
                
                if health_status == 'HEALTHY':
                    print(f"\n🎉 SUCCESS! Task is HEALTHY with Python-based health check!")
                elif health_status == 'UNHEALTHY':
                    print(f"\n⚠️  Task is still UNHEALTHY. Further investigation needed.")
                else:
                    print(f"\n⏳ Health status is {health_status}. May need more time.")
        
    else:
        print(f"\n⚠️  Deployment did not complete within {timeout} seconds")
        print(f"   Check AWS console for deployment status")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'old_revision': current_revision,
        'new_revision': new_revision,
        'old_health_check': current_task_def['containerDefinitions'][0].get('healthCheck'),
        'new_health_check': new_health_check,
        'deployment_time_seconds': int(time.time() - start_time) if deployment_complete else None,
        'deployment_complete': deployment_complete
    }
    
    output_file = f'health-check-fix-{int(time.time())}.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📝 Results saved to: {output_file}")
    print("="*80)

if __name__ == '__main__':
    fix_health_check_command()
