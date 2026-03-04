#!/usr/bin/env python3
"""
Increase ECS task memory to 20GB (20480 MB) and redeploy.
This resolves OOM kills by providing sufficient memory for the application.
"""

import boto3
import json
import sys
import time
from datetime import datetime
from pathlib import Path

def increase_to_20gb():
    """Increase task memory to 20GB and redeploy."""
    
    # Configuration
    MEMORY_MB = 20480  # 20 GB
    CPU_UNITS = 4096   # Required CPU for 20GB memory on Fargate
    CLUSTER_NAME = "multimodal-lib-prod-cluster"
    SERVICE_NAME = "multimodal-lib-prod-service"
    
    ecs = boto3.client('ecs')
    
    print("=" * 80)
    print("INCREASING TASK MEMORY TO 20GB")
    print("=" * 80)
    print()
    print(f"Target Configuration:")
    print(f"  Memory: {MEMORY_MB} MB (20 GB)")
    print(f"  CPU: {CPU_UNITS} units (4 vCPUs)")
    print(f"  Cluster: {CLUSTER_NAME}")
    print(f"  Service: {SERVICE_NAME}")
    print()
    
    # Step 1: Get current task definition
    print("Step 1: Getting current task definition...")
    try:
        service_response = ecs.describe_services(
            cluster=CLUSTER_NAME,
            services=[SERVICE_NAME]
        )
        
        if not service_response['services']:
            print(f"❌ Service {SERVICE_NAME} not found")
            sys.exit(1)
        
        current_task_def_arn = service_response['services'][0]['taskDefinition']
        current_task_def_name = current_task_def_arn.split('/')[-1].split(':')[0]
        
        print(f"✓ Current task definition: {current_task_def_arn}")
        
        # Get full task definition
        task_def_response = ecs.describe_task_definition(
            taskDefinition=current_task_def_arn
        )
        
        task_def = task_def_response['taskDefinition']
        current_memory = task_def['memory']
        current_cpu = task_def['cpu']
        
        print(f"  Current Memory: {current_memory} MB")
        print(f"  Current CPU: {current_cpu} units")
        print()
        
    except Exception as e:
        print(f"❌ Failed to get current task definition: {e}")
        sys.exit(1)
    
    # Step 2: Create new task definition with 20GB memory
    print(f"Step 2: Creating new task definition with {MEMORY_MB} MB memory...")
    
    # Prepare new task definition
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def['networkMode'],
        'containerDefinitions': task_def['containerDefinitions'],
        'volumes': task_def.get('volumes', []),
        'placementConstraints': task_def.get('placementConstraints', []),
        'requiresCompatibilities': task_def.get('requiresCompatibilities', ['FARGATE']),
        'cpu': str(CPU_UNITS),
        'memory': str(MEMORY_MB),
    }
    
    # Add optional fields if present
    if 'tags' in task_def:
        new_task_def['tags'] = task_def['tags']
    if 'proxyConfiguration' in task_def:
        new_task_def['proxyConfiguration'] = task_def['proxyConfiguration']
    if 'ephemeralStorage' in task_def:
        new_task_def['ephemeralStorage'] = task_def['ephemeralStorage']
    
    try:
        register_response = ecs.register_task_definition(**new_task_def)
        new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
        new_revision = register_response['taskDefinition']['revision']
        print(f"✓ New task definition created: {current_task_def_name}:{new_revision}")
        print(f"  Memory: {MEMORY_MB} MB (20 GB)")
        print(f"  CPU: {CPU_UNITS} units (4 vCPUs)")
        print()
    except Exception as e:
        print(f"❌ Failed to create new task definition: {e}")
        sys.exit(1)
    
    # Step 3: Update service to use new task definition
    print("Step 3: Updating service with new task definition...")
    try:
        update_response = ecs.update_service(
            cluster=CLUSTER_NAME,
            service=SERVICE_NAME,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True
        )
        print(f"✓ Service updated successfully")
        deployment_id = update_response['service']['deployments'][0]['id']
        print(f"  Deployment ID: {deployment_id}")
        print()
    except Exception as e:
        print(f"❌ Failed to update service: {e}")
        sys.exit(1)
    
    # Step 4: Monitor deployment
    print("Step 4: Monitoring deployment...")
    print("  This may take 5-10 minutes...")
    print()
    
    max_wait = 600  # 10 minutes
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < max_wait:
        try:
            service_response = ecs.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            service = service_response['services'][0]
            deployments = service['deployments']
            
            # Find the new deployment
            for deployment in deployments:
                if deployment['taskDefinition'] == new_task_def_arn:
                    running_count = deployment['runningCount']
                    desired_count = deployment['desiredCount']
                    status = deployment['status']
                    
                    current_status = f"  Status: {status} | Running: {running_count}/{desired_count} tasks"
                    
                    if current_status != last_status:
                        print(current_status)
                        last_status = current_status
                    
                    if running_count == desired_count and status == 'PRIMARY':
                        print()
                        print("✓ Deployment complete!")
                        print()
                        break
            else:
                time.sleep(15)
                continue
            break
            
        except Exception as e:
            print(f"  Error checking deployment status: {e}")
            time.sleep(15)
            continue
    else:
        print()
        print("⚠️  Deployment taking longer than expected")
        print("   Check AWS Console for detailed status")
        print()
    
    # Step 5: Verify new tasks
    print("Step 5: Verifying new tasks...")
    try:
        tasks_response = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME,
            desiredStatus='RUNNING'
        )
        
        if tasks_response['taskArns']:
            tasks_detail = ecs.describe_tasks(
                cluster=CLUSTER_NAME,
                tasks=tasks_response['taskArns']
            )
            
            print(f"✓ Found {len(tasks_detail['tasks'])} running task(s)")
            print()
            
            for task in tasks_detail['tasks']:
                task_id = task['taskArn'].split('/')[-1][:12]
                task_def = task['taskDefinitionArn'].split('/')[-1]
                memory = task.get('memory', 'N/A')
                cpu = task.get('cpu', 'N/A')
                
                print(f"  Task {task_id}:")
                print(f"    Task Definition: {task_def}")
                print(f"    Memory: {memory} MB")
                print(f"    CPU: {cpu} units")
                print()
        else:
            print("⚠️  No running tasks found")
            print()
            
    except Exception as e:
        print(f"⚠️  Failed to verify tasks: {e}")
        print()
    
    # Summary
    print("=" * 80)
    print("MEMORY INCREASE COMPLETE!")
    print("=" * 80)
    print()
    print("📋 Summary:")
    print(f"  • Old Memory: {current_memory} MB ({int(current_memory)/1024:.1f} GB)")
    print(f"  • New Memory: {MEMORY_MB} MB (20 GB)")
    print(f"  • Increase: +{MEMORY_MB - int(current_memory)} MB (+{(MEMORY_MB - int(current_memory))/1024:.1f} GB)")
    print(f"  • Old CPU: {current_cpu} units")
    print(f"  • New CPU: {CPU_UNITS} units")
    print(f"  • Task Definition: {current_task_def_name}:{new_revision}")
    print()
    
    # Cost calculation
    print("💰 Cost Impact (approximate):")
    # Fargate pricing: $0.04048 per vCPU per hour + $0.004445 per GB per hour
    old_cpu_cost = int(current_cpu) / 1024 * 0.04048 * 730
    new_cpu_cost = CPU_UNITS / 1024 * 0.04048 * 730
    old_mem_cost = int(current_memory) / 1024 * 0.004445 * 730
    new_mem_cost = MEMORY_MB / 1024 * 0.004445 * 730
    
    old_total = old_cpu_cost + old_mem_cost
    new_total = new_cpu_cost + new_mem_cost
    
    print(f"  • Old Cost: ~${old_total:.2f}/month")
    print(f"  • New Cost: ~${new_total:.2f}/month")
    print(f"  • Increase: ~${new_total - old_total:.2f}/month")
    print()
    
    print("✅ Next Steps:")
    print("  1. Monitor for OOM kills (should be eliminated)")
    print("  2. Check CloudWatch memory metrics")
    print("  3. Verify application is running smoothly")
    print("  4. Consider memory optimization if usage is still high")
    print()
    
    print("📊 Monitor memory usage:")
    print(f"   aws cloudwatch get-metric-statistics \\")
    print(f"     --namespace AWS/ECS \\")
    print(f"     --metric-name MemoryUtilization \\")
    print(f"     --dimensions Name=ClusterName,Value={CLUSTER_NAME} \\")
    print(f"                  Name=ServiceName,Value={SERVICE_NAME} \\")
    print(f"     --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \\")
    print(f"     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \\")
    print(f"     --period 300 \\")
    print(f"     --statistics Average,Maximum")
    print()
    
    # Save deployment record
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        record_file = Path(__file__).parent.parent / f"20gb-deployment-{timestamp}.json"
        
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": "increase_memory_to_20gb",
            "old_memory_mb": int(current_memory),
            "new_memory_mb": MEMORY_MB,
            "old_cpu_units": int(current_cpu),
            "new_cpu_units": CPU_UNITS,
            "task_definition": f"{current_task_def_name}:{new_revision}",
            "deployment_id": deployment_id,
            "cluster": CLUSTER_NAME,
            "service": SERVICE_NAME
        }
        
        with open(record_file, 'w') as f:
            json.dump(record, f, indent=2)
        
        print(f"📝 Deployment record saved: {record_file}")
        print()
        
    except Exception as e:
        print(f"⚠️  Failed to save deployment record: {e}")
        print()

if __name__ == "__main__":
    print()
    print("This script will increase your ECS task memory to 20GB (20480 MB)")
    print("and redeploy the service.")
    print()
    
    response = input("Do you want to continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Aborted.")
        sys.exit(0)
    
    print()
    increase_to_20gb()
