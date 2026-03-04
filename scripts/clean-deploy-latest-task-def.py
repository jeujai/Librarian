#!/usr/bin/env python3
"""
Clean deployment with latest task definition.

This script:
1. Gets the latest ACTIVE task definition
2. Forces a new deployment using it
3. Deregisters old task definition revisions (marks them inactive)
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("CLEAN DEPLOYMENT WITH LATEST TASK DEFINITION")
    print("=" * 80)
    print()
    
    # Get all task definition revisions
    print("📋 Fetching all task definition revisions...")
    response = ecs.list_task_definitions(
        familyPrefix='multimodal-lib-prod-app',
        status='ACTIVE',
        sort='DESC'
    )
    
    task_defs = response['taskDefinitionArns']
    print(f"   Found {len(task_defs)} ACTIVE revisions")
    
    if not task_defs:
        print("   ❌ No active task definitions found!")
        return
    
    latest_task_def = task_defs[0]
    latest_revision = latest_task_def.split(':')[-1]
    
    print(f"   Latest revision: {latest_revision}")
    print()
    
    # Force new deployment with latest
    print(f"🚀 Forcing new deployment with revision {latest_revision}...")
    ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=latest_task_def,
        forceNewDeployment=True
    )
    print("   ✓ Deployment initiated")
    print()
    
    # Deregister old revisions (keep latest 3)
    if len(task_defs) > 3:
        print(f"🗑️  Deregistering old task definition revisions (keeping latest 3)...")
        for old_task_def in task_defs[3:]:
            old_revision = old_task_def.split(':')[-1]
            try:
                ecs.deregister_task_definition(taskDefinition=old_task_def)
                print(f"   ✓ Deregistered revision {old_revision}")
            except Exception as e:
                print(f"   ⚠️  Could not deregister revision {old_revision}: {e}")
        print()
    
    print("=" * 80)
    print("✅ DEPLOYMENT COMPLETE")
    print("=" * 80)
    print()
    print(f"Service is now deploying with task definition revision {latest_revision}")
    print()
    print("Monitor deployment:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster \\")
    print("    --services multimodal-lib-prod-service \\")
    print("    --query 'services[0].{TaskDef:taskDefinition,Running:runningCount,Desired:desiredCount}'")
    print()
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'latest_revision': latest_revision,
        'total_active_revisions': len(task_defs),
        'deregistered_count': max(0, len(task_defs) - 3)
    }
    
    filename = f"clean-deploy-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {filename}")
    print()

if __name__ == '__main__':
    main()
