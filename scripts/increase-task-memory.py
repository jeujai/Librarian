#!/usr/bin/env python3
"""
Increase ECS task memory to resolve OOM kills.
Updates task definition with new memory limit and redeploys.
Also updates config/deployment-config.json to preserve settings.
"""

import boto3
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Configuration file path
CONFIG_FILE = Path(__file__).parent.parent / "config" / "deployment-config.json"

def update_config_file(memory_mb, cpu_units, cluster_name, service_name):
    """Update deployment configuration file with new memory settings."""
    try:
        # Load existing config or create new one
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "task_memory_mb": 4096,
                "task_cpu_units": 2048,
                "desired_count": 1,
                "cluster_name": cluster_name,
                "service_name": service_name,
                "task_family": "multimodal-lib-prod-app",
                "container_name": "multimodal-lib-prod-app",
                "notes": {
                    "memory_history": [],
                    "optimization_opportunities": [
                        "Implement lazy model loading to reduce peak memory",
                        "Use model quantization to reduce model size",
                        "Consider smaller model variants",
                        "Implement model unloading for unused models"
                    ]
                }
            }
        
        # Update memory and CPU
        old_memory = config.get('task_memory_mb', 4096)
        config['task_memory_mb'] = memory_mb
        config['task_cpu_units'] = cpu_units
        config['cluster_name'] = cluster_name
        config['service_name'] = service_name
        
        # Add to history
        if 'notes' not in config:
            config['notes'] = {'memory_history': []}
        if 'memory_history' not in config['notes']:
            config['notes']['memory_history'] = []
        
        config['notes']['memory_history'].append({
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'memory_mb': memory_mb,
            'cpu_units': cpu_units,
            'reason': f'Increased from {old_memory}MB to {memory_mb}MB via increase-task-memory.py'
        })
        
        # Ensure config directory exists
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Save updated config
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✓ Configuration file updated: {CONFIG_FILE}")
        print(f"  Memory: {old_memory}MB → {memory_mb}MB")
        print(f"  CPU: {cpu_units} units")
        print()
        
        return True
        
    except Exception as e:
        print(f"⚠️  Failed to update configuration file: {e}")
        print("   Deployment will continue but settings may not persist")
        print()
        return False

def increase_task_memory(memory_mb, cpu_units=None, cluster_name="multimodal-lib-prod-cluster", 
                        service_name="multimodal-lib-prod-service"):
    """Increase task memory and optionally CPU."""
    
    ecs = boto3.client('ecs')
    
    print("=" * 80)
    print("INCREASING ECS TASK MEMORY")
    print("=" * 80)
    print()
    
    # Step 0: Update configuration file
    print("0. Updating deployment configuration file...")
    update_config_file(memory_mb, cpu_units, cluster_name, service_name)
    
    # Step 1: Get current task definition
    print("1. Getting current task definition...")
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"❌ Service {service_name} not found")
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
    
    # Step 2: Create new task definition with increased memory
    print(f"2. Creating new task definition with {memory_mb} MB memory...")
    
    # Remove fields that can't be in register_task_definition
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def['networkMode'],
        'containerDefinitions': task_def['containerDefinitions'],
        'volumes': task_def.get('volumes', []),
        'placementConstraints': task_def.get('placementConstraints', []),
        'requiresCompatibilities': task_def.get('requiresCompatibilities', ['FARGATE']),
        'cpu': str(cpu_units) if cpu_units else task_def['cpu'],
        'memory': str(memory_mb),
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
        print(f"  New Memory: {memory_mb} MB")
        if cpu_units:
            print(f"  New CPU: {cpu_units} units")
        print()
    except Exception as e:
        print(f"❌ Failed to create new task definition: {e}")
        sys.exit(1)
    
    # Step 3: Update service to use new task definition
    print("3. Updating service with new task definition...")
    try:
        update_response = ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            taskDefinition=new_task_def_arn,
            forceNewDeployment=True
        )
        print(f"✓ Service updated successfully")
        print(f"  Deployment ID: {update_response['service']['deployments'][0]['id']}")
        print()
    except Exception as e:
        print(f"❌ Failed to update service: {e}")
        sys.exit(1)
    
    # Step 4: Monitor deployment
    print("4. Monitoring deployment...")
    print("  Waiting for new tasks to start...")
    print()
    
    import time
    max_wait = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        service_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_response['services'][0]
        deployments = service['deployments']
        
        # Check if new deployment is primary
        for deployment in deployments:
            if deployment['taskDefinition'] == new_task_def_arn:
                running_count = deployment['runningCount']
                desired_count = deployment['desiredCount']
                
                print(f"  Running: {running_count}/{desired_count} tasks", end='\r')
                
                if running_count == desired_count and deployment['status'] == 'PRIMARY':
                    print()
                    print("✓ Deployment complete!")
                    print()
                    break
        else:
            time.sleep(10)
            continue
        break
    else:
        print()
        print("⚠️  Deployment taking longer than expected")
        print("   Check AWS Console for status")
        print()
    
    # Step 5: Verify new tasks
    print("5. Verifying new tasks...")
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        tasks_detail = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
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
    
    # Summary
    print("=" * 80)
    print("MEMORY INCREASE COMPLETE!")
    print("=" * 80)
    print()
    print("📋 Summary:")
    print(f"  • Old Memory: {current_memory} MB")
    print(f"  • New Memory: {memory_mb} MB")
    print(f"  • Increase: +{memory_mb - int(current_memory)} MB")
    print(f"  • Task Definition: {current_task_def_name}:{new_revision}")
    print()
    print("📊 Cost Impact:")
    old_cost = int(current_memory) * 0.0000125 * 730  # per month
    new_cost = memory_mb * 0.0000125 * 730
    print(f"  • Old Cost: ~${old_cost:.2f}/month")
    print(f"  • New Cost: ~${new_cost:.2f}/month")
    print(f"  • Increase: ~${new_cost - old_cost:.2f}/month")
    print()
    print("🔍 Next Steps:")
    print("  1. Monitor for OOM kills (should be zero now)")
    print("  2. Check CloudWatch memory metrics")
    print("  3. Consider optimizing code to reduce memory usage")
    print()
    print("📊 Monitor memory usage:")
    print(f"   aws cloudwatch get-metric-statistics \\")
    print(f"     --namespace AWS/ECS \\")
    print(f"     --metric-name MemoryUtilization \\")
    print(f"     --dimensions Name=ClusterName,Value={cluster_name} \\")
    print(f"     --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \\")
    print(f"     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \\")
    print(f"     --period 300 \\")
    print(f"     --statistics Average,Maximum")
    print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Increase ECS task memory")
    parser.add_argument("--memory", type=int, required=True, help="New memory limit in MB (e.g., 8192)")
    parser.add_argument("--cpu", type=int, help="New CPU units (optional, e.g., 2048)")
    parser.add_argument("--cluster", default="multimodal-lib-prod-cluster", help="ECS cluster name")
    parser.add_argument("--service", default="multimodal-lib-prod-service", help="ECS service name")
    
    args = parser.parse_args()
    
    # Validate memory/CPU combinations for Fargate
    valid_combinations = {
        512: [256],
        1024: [256, 512],
        2048: [256, 512, 1024],
        3072: [512, 1024],
        4096: [512, 1024, 2048],
        5120: [1024, 2048],
        6144: [1024, 2048],
        7168: [1024, 2048],
        8192: [1024, 2048, 4096],
        16384: [2048, 4096],
        30720: [4096],
    }
    
    if args.memory not in valid_combinations:
        print(f"❌ Invalid memory value: {args.memory}")
        print(f"   Valid values: {', '.join(map(str, valid_combinations.keys()))}")
        sys.exit(1)
    
    if args.cpu and args.cpu not in valid_combinations[args.memory]:
        print(f"❌ Invalid CPU value {args.cpu} for memory {args.memory}")
        print(f"   Valid CPU values for {args.memory}MB: {', '.join(map(str, valid_combinations[args.memory]))}")
        sys.exit(1)
    
    increase_task_memory(args.memory, args.cpu, args.cluster, args.service)
