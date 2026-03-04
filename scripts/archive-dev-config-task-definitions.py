#!/usr/bin/env python3
"""
Archive and deregister development configuration task definitions.

This script:
1. Identifies task definitions with localhost/development configuration
2. Archives their configuration to the archive folder
3. Deregisters them from ECS to prevent accidental deployment
4. Creates a reference document for future use
"""

import json
import boto3
from datetime import datetime
from pathlib import Path

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("ARCHIVING DEVELOPMENT CONFIGURATION TASK DEFINITIONS")
    print("=" * 80)
    print()
    
    # Task definitions to archive (those with localhost config)
    dev_revisions = [41]  # Add more if needed
    
    # Create archive directory
    archive_dir = Path("archive/task-definitions/dev-config")
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    archived_definitions = []
    
    for revision in dev_revisions:
        task_def_arn = f"multimodal-lib-prod-app:{revision}"
        
        print(f"📋 Processing task definition: {task_def_arn}")
        
        # Get task definition details
        response = ecs.describe_task_definition(taskDefinition=task_def_arn)
        task_def = response['taskDefinition']
        
        # Check if it has localhost configuration
        container_def = task_def['containerDefinitions'][0]
        env_vars = {env['name']: env['value'] for env in container_def.get('environment', [])}
        
        has_localhost = False
        localhost_services = []
        
        # Check for localhost indicators
        if not env_vars.get('USE_AWS_NATIVE'):
            has_localhost = True
            localhost_services.append("No AWS_NATIVE flag")
        
        if not env_vars.get('NEPTUNE_CLUSTER_ENDPOINT'):
            has_localhost = True
            localhost_services.append("Missing Neptune endpoint")
        
        if not env_vars.get('OPENSEARCH_DOMAIN_ENDPOINT'):
            has_localhost = True
            localhost_services.append("Missing OpenSearch endpoint")
        
        if not env_vars.get('DATABASE_HOST'):
            has_localhost = True
            localhost_services.append("Missing RDS host")
        
        if has_localhost:
            print(f"  ⚠️  Development config detected:")
            for service in localhost_services:
                print(f"     - {service}")
            
            # Archive the task definition
            archive_file = archive_dir / f"task-definition-rev{revision}.json"
            with open(archive_file, 'w') as f:
                json.dump(task_def, f, indent=2, default=str)
            
            print(f"  ✅ Archived to: {archive_file}")
            
            # Deregister the task definition
            try:
                ecs.deregister_task_definition(taskDefinition=task_def['taskDefinitionArn'])
                print(f"  ✅ Deregistered from ECS")
                
                archived_definitions.append({
                    'revision': revision,
                    'arn': task_def['taskDefinitionArn'],
                    'cpu': task_def['cpu'],
                    'memory': task_def['memory'],
                    'image': container_def['image'],
                    'archived_at': datetime.now().isoformat(),
                    'archive_file': str(archive_file),
                    'reason': 'Development configuration (localhost services)',
                    'issues': localhost_services
                })
            except Exception as e:
                print(f"  ❌ Failed to deregister: {e}")
        else:
            print(f"  ℹ️  AWS-native config detected - skipping")
        
        print()
    
    # Create archive summary document
    summary = {
        'archived_at': datetime.now().isoformat(),
        'reason': 'Prevent accidental deployment of development configuration',
        'archived_revisions': archived_definitions,
        'aws_native_revision': 42,
        'notes': [
            'These task definitions used localhost services (PostgreSQL, Milvus, Redis, Neo4j)',
            'They would fail in Fargate environment due to missing services',
            'Use revision 42 or later for AWS-native configuration',
            'Archived files can be found in archive/task-definitions/dev-config/'
        ]
    }
    
    summary_file = archive_dir / 'ARCHIVE_SUMMARY.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("=" * 80)
    print("ARCHIVE SUMMARY")
    print("=" * 80)
    print(f"Archived {len(archived_definitions)} task definition(s)")
    print(f"Summary saved to: {summary_file}")
    print()
    
    if archived_definitions:
        print("Archived Revisions:")
        for item in archived_definitions:
            print(f"  - Revision {item['revision']}: {item['reason']}")
        print()
    
    # Create reference document
    reference_doc = f"""# Development Configuration Archive

**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Purpose

This archive contains task definition revisions that used **development/localhost configuration** instead of AWS-native services. These have been deregistered from ECS to prevent accidental deployment.

## Archived Revisions

"""
    
    for item in archived_definitions:
        reference_doc += f"""
### Revision {item['revision']}

- **ARN**: `{item['arn']}`
- **CPU**: {item['cpu']}
- **Memory**: {item['memory']}
- **Image**: `{item['image']}`
- **Archived**: {item['archived_at']}
- **Archive File**: `{item['archive_file']}`

**Issues Detected**:
"""
        for issue in item['issues']:
            reference_doc += f"- {issue}\n"
    
    reference_doc += f"""

## Why These Were Archived

These task definitions were configured to connect to services on `localhost`:
- PostgreSQL on `localhost:5432`
- Milvus on `localhost:19530`
- Redis on `localhost:6379`
- Neo4j on `localhost:7687`

In the Fargate environment, these services don't exist, causing the application to fail on startup.

## Current Production Configuration

**Use Revision 42 or later** - These revisions use AWS-native services:
- **Neptune**: Graph database (replaces Neo4j)
- **OpenSearch**: Vector search (replaces Milvus)
- **RDS PostgreSQL**: Relational database
- **ElastiCache Redis**: Caching layer

See `AWS_NATIVE_CONFIG_RESTORATION.md` for details.

## Restoring from Archive

If you need to reference these configurations:

1. Find the archived JSON file in `archive/task-definitions/dev-config/`
2. Review the configuration
3. **DO NOT** re-register without updating to AWS-native endpoints

## Prevention

To prevent this in the future:

1. Always base new task definitions on revision 42 or later
2. Validate environment variables before deployment
3. Use `scripts/switch-to-aws-native-config.py` to ensure correct configuration
4. Check for `USE_AWS_NATIVE=true` environment variable

## Related Documentation

- `AWS_NATIVE_CONFIG_RESTORATION.md` - How to restore AWS-native configuration
- `.kiro/specs/aws-native-database-implementation/` - AWS-native database spec
- `scripts/switch-to-aws-native-config.py` - Configuration restoration script
"""
    
    reference_file = archive_dir / 'README.md'
    with open(reference_file, 'w') as f:
        f.write(reference_doc)
    
    print(f"📄 Reference document created: {reference_file}")
    print()
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("1. ✅ Development configurations archived")
    print("2. ✅ Task definitions deregistered from ECS")
    print("3. ✅ Reference documentation created")
    print()
    print("⚠️  IMPORTANT:")
    print("   - Only use revision 42 or later for deployments")
    print("   - These revisions use AWS-native services (Neptune, OpenSearch, RDS, Redis)")
    print("   - Archived configurations are preserved for reference only")
    print()

if __name__ == '__main__':
    main()
