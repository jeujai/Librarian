#!/usr/bin/env python3
"""
Update ECS task definition memory to 8GB without rebuilding the Docker image.
This uses the existing image and only updates the memory/CPU configuration.
"""

import boto3
import json
from datetime import datetime
from pathlib import Path

# New memory configuration
NEW_MEMORY_MB = 8192  # 8GB
NEW_CPU_UNITS = 4096  # 4 vCPUs (required for 8GB memory)

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
TASK_FAMILY = "multimodal-lib-prod-app"

# Configuration file path
CONFIG_FILE = Path(__file__).parent.parent / "config" / "deployment-config.json"

def update_deployment_config():
    """Update deployment configuration file with new memory settings."""
    print("📝 Updating deployment configuration file...")
    
    # Ensure config directory exists
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing config or create new one
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"⚠️  Error loading config: {e}")
            config = {}
    else:
        config = {}
    
    # Update memory and CPU settings
    old_memory = config.get('task_memory_mb', 'unknown')
    old_cpu = config.get('task_cpu_units', 'unknown')
    
    config.update({
        'task_memory_mb': NEW_MEMORY_MB,
        'task_cpu_units': NEW_CPU_UNITS,
        'desired_count': config.get('desired_count', 1),
        'cluster_name': CLUSTER_NAME,
        'service_name': SERVICE_NAME,
        'task_family': TASK_FAMILY,
        'container_name': config.get('container_name', 'multimodal-lib-prod-app')
    })
    
    # Save updated configuration
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Configuration file updated")
    print(f"   Old Memory: {old_memory} MB")
    print(f"   New Memory: {NEW_MEMORY_MB} MB (8GB)")
    print(f"   Old CPU: {old_cpu} units")
    print(f"   New CPU: {NEW_CPU_UNITS} units (4 vCPUs)")

def update_task_definition_memory():
    """Update task definition with new memory settings."""
    print("\n🔧 Updating ECS task definition...")
    
    ecs = boto3.client('ecs')
    
    try:
        # Get current task definition
        print(f"📋 Fetching current task definition: {TASK_FAMILY}")
        task_def_response = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)
        current_task_def = task_def_response['taskDefinition']
        
        old_memory = current_task_def.get('memory', 'unknown')
        old_cpu = current_task_def.get('cpu', 'unknown')
        
        print(f"   Current Memory: {old_memory} MB")
        print(f"   Current CPU: {old_cpu} units")
        
        # Create new task definition with updated memory/CPU
        new_task_def = {
            'family': current_task_def['family'],
            'taskRoleArn': current_task_def.get('taskRoleArn'),
            'executionRoleArn': current_task_def.get('executionRoleArn'),
            'networkMode': current_task_def['networkMode'],
            'requiresCompatibilities': current_task_def['requiresCompatibilities'],
            'cpu': str(NEW_CPU_UNITS),
            'memory': str(NEW_MEMORY_MB),
            'containerDefinitions': current_task_def['containerDefinitions']
        }
        
        # Add ephemeral storage if present
        if 'ephemeralStorage' in current_task_def:
            new_task_def['ephemeralStorage'] = current_task_def['ephemeralStorage']
        
        # Register new task definition
        print(f"📝 Registering new task definition...")
        print(f"   New Memory: {NEW_MEMORY_MB} MB (8GB)")
        print(f"   New CPU: {NEW_CPU_UNITS} units (4 vCPUs)")
        
        register_response = ecs.register_task_definition(**new_task_def)
        new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
        
        print(f"✅ New task definition registered")
        print(f"   ARN: {new_task_def_arn}")
        
        return new_task_def_arn
        
    except Exception as e:
        print(f"❌ Error updating task definition: {e}")
        raise

def update_ecs_service(task_def_arn):
    """Update ECS service to use new task definition."""
    print(f"\n🚀 Updating ECS service...")
    
    ecs = boto3.client('ecs')
    
    try:
        print(f"   Cluster: {CLUSTER_NAME}")
        print(f"   Service: {SERVICE_NAME}")
        print(f"   Task Definition: {task_def_arn}")
        
        # Update service
        update_response = ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            taskDefinition=task_def_arn,
            forceNewDeployment=True
        )
        
        print(f"✅ Service update initiated")
        print(f"   Deployment ID: {update_response['service']['deployments'][0]['id']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating service: {e}")
        raise

def wait_for_deployment():
    """Wait for deployment to stabilize."""
    print(f"\n⏳ Waiting for deployment to complete...")
    print(f"   This may take 5-10 minutes...")
    
    ecs = boto3.client('ecs')
    
    try:
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME],
            WaiterConfig={
                'Delay': 15,
                'MaxAttempts': 40  # 10 minutes max
            }
        )
        
        print(f"✅ Deployment completed successfully")
        return True
        
    except Exception as e:
        print(f"⚠️  Deployment monitoring timeout (service may still be deploying): {e}")
        return False

def verify_deployment():
    """Verify the deployment status."""
    print(f"\n🔍 Verifying deployment...")
    
    ecs = boto3.client('ecs')
    
    try:
        # Get service status
        service_response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if service_response['services']:
            service = service_response['services'][0]
            running_count = service['runningCount']
            desired_count = service['desiredCount']
            
            print(f"📊 Service Status:")
            print(f"   Running tasks: {running_count}")
            print(f"   Desired tasks: {desired_count}")
            print(f"   Status: {service['status']}")
            
            # Get task details
            if service['deployments']:
                for deployment in service['deployments']:
                    print(f"\n   Deployment:")
                    print(f"      Status: {deployment['status']}")
                    print(f"      Running: {deployment['runningCount']}")
                    print(f"      Desired: {deployment['desiredCount']}")
                    print(f"      Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
            
            if running_count == desired_count and service['status'] == 'ACTIVE':
                print(f"\n✅ Service is healthy")
                return True
            else:
                print(f"\n⚠️  Service not fully healthy yet")
                return False
        else:
            print(f"❌ Service not found")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying deployment: {e}")
        return False

def main():
    """Main execution function."""
    print("🔧 Update ECS Task Memory to 8GB (No Rebuild)")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().isoformat()}")
    print()
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'target_memory_mb': NEW_MEMORY_MB,
        'target_cpu_units': NEW_CPU_UNITS,
        'steps': [],
        'success': True
    }
    
    try:
        # Step 1: Update configuration file
        print("1️⃣ Updating configuration file...")
        update_deployment_config()
        results['steps'].append({
            'step': 'config_update',
            'status': 'success'
        })
        
        # Step 2: Update task definition
        print("\n2️⃣ Updating task definition...")
        task_def_arn = update_task_definition_memory()
        results['steps'].append({
            'step': 'task_definition_update',
            'status': 'success',
            'task_definition_arn': task_def_arn
        })
        
        # Step 3: Update ECS service
        print("\n3️⃣ Updating ECS service...")
        update_ecs_service(task_def_arn)
        results['steps'].append({
            'step': 'service_update',
            'status': 'success'
        })
        
        # Step 4: Wait for deployment
        print("\n4️⃣ Waiting for deployment...")
        deployment_success = wait_for_deployment()
        results['steps'].append({
            'step': 'deployment_wait',
            'status': 'success' if deployment_success else 'warning'
        })
        
        # Step 5: Verify deployment
        print("\n5️⃣ Verifying deployment...")
        verification_success = verify_deployment()
        results['steps'].append({
            'step': 'deployment_verification',
            'status': 'success' if verification_success else 'warning'
        })
        
        print("\n" + "=" * 60)
        print("✅ Memory update completed!")
        print(f"\n📊 New Configuration:")
        print(f"   Memory: {NEW_MEMORY_MB} MB (8GB)")
        print(f"   CPU: {NEW_CPU_UNITS} units (4 vCPUs)")
        print(f"\n📋 Next Steps:")
        print(f"   1. Monitor CloudWatch logs for any issues")
        print(f"   2. Check application performance")
        print(f"   3. Verify memory usage stays within 8GB limit")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        results['success'] = False
        results['steps'].append({
            'step': 'fatal_error',
            'status': 'failed',
            'message': str(e)
        })
        return results
    finally:
        # Save results
        timestamp = int(datetime.now().timestamp())
        results_file = f'8gb-memory-update-{timestamp}.json'
        
        try:
            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n📝 Results saved to: {results_file}")
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")

if __name__ == "__main__":
    import sys
    results = main()
    sys.exit(0 if results['success'] else 1)
