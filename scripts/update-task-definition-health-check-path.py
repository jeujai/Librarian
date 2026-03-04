#!/usr/bin/env python3
"""
Update ECS Task Definition Health Check Path

This script updates the health check command in the ECS task definition
to use the correct API path: /api/health/minimal instead of /health/minimal

The health check router is mounted at /api/health, so the correct path should be:
- Current: curl -f http://localhost:8000/health/minimal || exit 1
- Updated: curl -f http://localhost:8000/api/health/minimal || exit 1
"""

import boto3
import json
import time
from datetime import datetime

def get_current_task_definition():
    """Get the current task definition for the multimodal-lib-prod service."""
    ecs = boto3.client('ecs')
    
    try:
        # Get the current service configuration
        response = ecs.describe_services(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service-alb']
        )
        
        if not response['services']:
            print("❌ Service 'multimodal-lib-prod-service-alb' not found")
            return None
            
        service = response['services'][0]
        current_task_def_arn = service['taskDefinition']
        
        print(f"📋 Current task definition: {current_task_def_arn}")
        
        # Get the task definition details
        task_def_response = ecs.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        return task_def_response['taskDefinition']
        
    except Exception as e:
        print(f"❌ Error getting current task definition: {e}")
        return None

def update_health_check_path(task_definition):
    """Update the health check command to use /api/health/minimal."""
    
    # Find the main application container
    app_container = None
    for container in task_definition['containerDefinitions']:
        if container['name'] == 'multimodal-lib-prod-app':
            app_container = container
            break
    
    if not app_container:
        print("❌ Application container 'multimodal-lib-prod-app' not found")
        return None
    
    # Check current health check
    if 'healthCheck' not in app_container:
        print("❌ No health check found in application container")
        return None
    
    current_command = app_container['healthCheck']['command']
    print(f"📋 Current health check command: {current_command}")
    
    # Update the health check command
    old_path = "http://localhost:8000/health/minimal"
    new_path = "http://localhost:8000/api/health/minimal"
    
    updated_command = []
    for cmd_part in current_command:
        if old_path in cmd_part:
            updated_cmd_part = cmd_part.replace(old_path, new_path)
            updated_command.append(updated_cmd_part)
            print(f"✅ Updated command part: {cmd_part} -> {updated_cmd_part}")
        else:
            updated_command.append(cmd_part)
    
    app_container['healthCheck']['command'] = updated_command
    
    print(f"📋 New health check command: {updated_command}")
    
    return task_definition

def create_new_task_definition(updated_task_def):
    """Create a new task definition with the updated health check."""
    ecs = boto3.client('ecs')
    
    # Remove fields that shouldn't be included in the new task definition
    fields_to_remove = [
        'taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
        'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy'
    ]
    
    for field in fields_to_remove:
        updated_task_def.pop(field, None)
    
    try:
        print("🚀 Creating new task definition...")
        response = ecs.register_task_definition(**updated_task_def)
        
        new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
        new_revision = response['taskDefinition']['revision']
        
        print(f"✅ Created new task definition: {new_task_def_arn}")
        print(f"📋 New revision: {new_revision}")
        
        return new_task_def_arn, new_revision
        
    except Exception as e:
        print(f"❌ Error creating new task definition: {e}")
        return None, None

def update_service_with_new_task_definition(new_task_def_arn):
    """Update the ECS service to use the new task definition."""
    ecs = boto3.client('ecs')
    
    try:
        print("🔄 Updating service with new task definition...")
        response = ecs.update_service(
            cluster='multimodal-lib-prod-cluster',
            service='multimodal-lib-prod-service-alb',
            taskDefinition=new_task_def_arn
        )
        
        print("✅ Service update initiated")
        return True
        
    except Exception as e:
        print(f"❌ Error updating service: {e}")
        return False

def wait_for_deployment_completion():
    """Wait for the deployment to complete."""
    ecs = boto3.client('ecs')
    
    print("⏳ Waiting for deployment to complete...")
    
    max_wait_time = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = ecs.describe_services(
                cluster='multimodal-lib-prod-cluster',
                services=['multimodal-lib-prod-service-alb']
            )
            
            service = response['services'][0]
            deployments = service['deployments']
            
            # Check if there's only one deployment (the new one) and it's stable
            if len(deployments) == 1 and deployments[0]['status'] == 'PRIMARY':
                running_count = deployments[0]['runningCount']
                desired_count = deployments[0]['desiredCount']
                
                if running_count == desired_count:
                    print("✅ Deployment completed successfully!")
                    return True
            
            # Show deployment progress
            for deployment in deployments:
                status = deployment['status']
                running = deployment['runningCount']
                desired = deployment['desiredCount']
                task_def = deployment['taskDefinition'].split('/')[-1]
                
                print(f"📊 Deployment {status}: {running}/{desired} tasks running ({task_def})")
            
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Error checking deployment status: {e}")
            return False
    
    print("⚠️ Deployment did not complete within the expected time")
    return False

def verify_health_check_update():
    """Verify that the health check path has been updated correctly."""
    print("🔍 Verifying health check update...")
    
    # Get the current task definition again
    current_task_def = get_current_task_definition()
    if not current_task_def:
        return False
    
    # Find the application container
    app_container = None
    for container in current_task_def['containerDefinitions']:
        if container['name'] == 'multimodal-lib-prod-app':
            app_container = container
            break
    
    if not app_container or 'healthCheck' not in app_container:
        print("❌ Could not find health check in current task definition")
        return False
    
    health_check_command = app_container['healthCheck']['command']
    command_str = ' '.join(health_check_command)
    
    if '/api/health/minimal' in command_str:
        print("✅ Health check path successfully updated to /api/health/minimal")
        print(f"📋 Current command: {health_check_command}")
        return True
    else:
        print("❌ Health check path was not updated correctly")
        print(f"📋 Current command: {health_check_command}")
        return False

def main():
    """Main execution function."""
    print("🏥 ECS Task Definition Health Check Path Update")
    print("=" * 60)
    print("Updating health check path from /health/minimal to /api/health/minimal")
    print()
    
    # Step 1: Get current task definition
    print("📋 Step 1: Getting current task definition...")
    current_task_def = get_current_task_definition()
    if not current_task_def:
        return
    
    print()
    
    # Step 2: Update health check path
    print("🔧 Step 2: Updating health check path...")
    updated_task_def = update_health_check_path(current_task_def)
    if not updated_task_def:
        return
    
    print()
    
    # Step 3: Create new task definition
    print("📝 Step 3: Creating new task definition...")
    new_task_def_arn, new_revision = create_new_task_definition(updated_task_def)
    if not new_task_def_arn:
        return
    
    print()
    
    # Step 4: Update service
    print("🔄 Step 4: Updating ECS service...")
    if not update_service_with_new_task_definition(new_task_def_arn):
        return
    
    print()
    
    # Step 5: Wait for deployment
    print("⏳ Step 5: Waiting for deployment completion...")
    if not wait_for_deployment_completion():
        print("⚠️ Deployment may still be in progress. Check AWS console for status.")
    
    print()
    
    # Step 6: Verify update
    print("✅ Step 6: Verifying health check update...")
    if verify_health_check_update():
        print()
        print("🎉 Health check path update completed successfully!")
        print()
        print("Summary:")
        print(f"  • Updated health check path to: /api/health/minimal")
        print(f"  • New task definition revision: {new_revision}")
        print(f"  • Service deployment: Completed")
        print()
        print("The ALB target group health check path (/api/health/minimal) now matches")
        print("the ECS task definition health check path.")
    else:
        print()
        print("❌ Health check path update verification failed!")
        print("Please check the AWS console for more details.")

if __name__ == "__main__":
    main()