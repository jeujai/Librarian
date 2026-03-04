#!/usr/bin/env python3
"""
Deregister all task definition revisions prior to 57 and force a clean redeployment.
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("DEREGISTER OLD TASK DEFINITIONS AND FORCE CLEAN REDEPLOY")
    print("=" * 80)
    print()
    
    # Get all task definition revisions
    print("📋 Fetching all task definition revisions...")
    response = ecs.list_task_definitions(
        familyPrefix='multimodal-lib-prod-app',
        status='ACTIVE',
        sort='ASC'  # Ascending to get oldest first
    )
    
    task_defs = response['taskDefinitionArns']
    print(f"   Found {len(task_defs)} ACTIVE revisions")
    print()
    
    # Deregister all revisions < 57
    print("🗑️  Deregistering all task definition revisions prior to 57...")
    deregistered = []
    for task_def_arn in task_defs:
        revision = int(task_def_arn.split(':')[-1])
        if revision < 57:
            try:
                ecs.deregister_task_definition(taskDefinition=task_def_arn)
                print(f"   ✓ Deregistered revision {revision}")
                deregistered.append(revision)
            except Exception as e:
                print(f"   ⚠️  Could not deregister revision {revision}: {e}")
    
    print(f"\n   Total deregistered: {len(deregistered)}")
    print()
    
    # Stop all running tasks to force fresh start
    print("🛑 Stopping all running tasks...")
    tasks_response = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service'
    )
    
    for task_arn in tasks_response['taskArns']:
        task_id = task_arn.split('/')[-1]
        try:
            ecs.stop_task(
                cluster='multimodal-lib-prod-cluster',
                task=task_arn,
                reason='Forcing clean redeployment with revision 57'
            )
            print(f"   ✓ Stopped task {task_id}")
        except Exception as e:
            print(f"   ⚠️  Could not stop task {task_id}: {e}")
    print()
    
    # Force new deployment with revision 57
    print("🚀 Forcing new deployment with revision 57...")
    latest_task_def = 'arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:57'
    
    ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=latest_task_def,
        forceNewDeployment=True
    )
    print("   ✓ Deployment initiated")
    print()
    
    print("=" * 80)
    print("✅ CLEANUP AND DEPLOYMENT COMPLETE")
    print("=" * 80)
    print()
    print(f"• Deregistered {len(deregistered)} old task definition revisions")
    print(f"• Stopped {len(tasks_response['taskArns'])} running tasks")
    print("• Forced new deployment with revision 57")
    print()
    print("Monitor deployment:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster \\")
    print("    --services multimodal-lib-prod-service \\")
    print("    --query 'services[0].deployments[*].{Status:status,TaskDef:taskDefinition,Running:runningCount,Desired:desiredCount}'")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'deregistered_revisions': deregistered,
        'stopped_tasks': len(tasks_response['taskArns']),
        'deployment_revision': 57
    }
    
    filename = f"deregister-and-redeploy-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {filename}")
    print()

if __name__ == '__main__':
    main()
