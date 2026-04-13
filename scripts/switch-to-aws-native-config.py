#!/usr/bin/env python3
"""
Switch ECS task definition to AWS-native database configuration.

This script creates a new task definition revision with the correct
environment variables for AWS-native services (Neptune, OpenSearch, RDS, ElastiCache)
instead of the development localhost configuration.
"""

import json
import sys
from datetime import datetime

import boto3


def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # AWS-Native Service Endpoints
    NEPTUNE_ENDPOINT = "multimodal-lib-prod-neptune.cluster-cq1iiac2gfkf.us-east-1.neptune.amazonaws.com"
    OPENSEARCH_ENDPOINT = "vpc-multimodal-lib-prod-search-2mjsemd5qwcuj3ezeltxxmwkrq.us-east-1.es.amazonaws.com"
    RDS_ENDPOINT = "multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com"
    REDIS_ENDPOINT = "master.multimodal-lib-prod-redis.znjbcw.use1.cache.amazonaws.com"
    
    print("=" * 80)
    print("SWITCHING TO AWS-NATIVE DATABASE CONFIGURATION")
    print("=" * 80)
    print()
    
    # Get current task definition (revision 41)
    print("📋 Fetching current task definition (revision 41)...")
    response = ecs.describe_task_definition(taskDefinition='multimodal-lib-prod-app:41')
    task_def = response['taskDefinition']
    
    print(f"✓ Current revision: {task_def['revision']}")
    print(f"  CPU: {task_def['cpu']}")
    print(f"  Memory: {task_def['memory']}")
    print()
    
    # Prepare new task definition with AWS-native configuration
    container_def = task_def['containerDefinitions'][0]
    
    # AWS-Native Environment Variables
    aws_native_env = [
        # Basic API Configuration
        {"name": "API_HOST", "value": "0.0.0.0"},
        {"name": "API_PORT", "value": "8000"},
        {"name": "API_WORKERS", "value": "4"},
        {"name": "LOG_LEVEL", "value": "INFO"},
        {"name": "DEBUG", "value": "false"},
        
        # Python Configuration
        {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
        {"name": "PYTHONUNBUFFERED", "value": "1"},
        
        # AWS-Native Database Configuration
        {"name": "USE_AWS_NATIVE", "value": "true"},
        {"name": "NEPTUNE_CLUSTER_ENDPOINT", "value": NEPTUNE_ENDPOINT},
        {"name": "NEPTUNE_PORT", "value": "8182"},
        {"name": "OPENSEARCH_DOMAIN_ENDPOINT", "value": f"https://{OPENSEARCH_ENDPOINT}"},
        {"name": "OPENSEARCH_PORT", "value": "443"},
        
        # PostgreSQL RDS Configuration
        {"name": "DATABASE_HOST", "value": RDS_ENDPOINT},
        {"name": "DATABASE_PORT", "value": "5432"},
        {"name": "DATABASE_NAME", "value": "multimodal_librarian"},
        {"name": "DATABASE_USER", "value": "postgres"},
        
        # Redis ElastiCache Configuration
        {"name": "REDIS_HOST", "value": REDIS_ENDPOINT},
        {"name": "REDIS_PORT", "value": "6379"},
        
        # AWS Region
        {"name": "AWS_DEFAULT_REGION", "value": "us-east-1"},
        {"name": "AWS_REGION", "value": "us-east-1"},
        
        # Document Processing Configuration
        {"name": "MAX_FILE_SIZE", "value": "10737418240"},  # 10GB - effectively unlimited
        {"name": "CHUNK_SIZE", "value": "512"},
        {"name": "CHUNK_OVERLAP", "value": "50"},
        {"name": "EMBEDDING_MODEL", "value": "all-MiniLM-L6-v2"},
        
        # External APIs
        {"name": "CONCEPTNET_API_BASE", "value": "http://api.conceptnet.io"},
        {"name": "YAGO_ENDPOINT", "value": "https://yago-knowledge.org/sparql/query"},
    ]
    
    # Add secrets for database password and other credentials
    secrets = [
        {
            "name": "DATABASE_PASSWORD",
            "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB:password::"
        },
        {
            "name": "REDIS_PASSWORD",
            "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/redis-7UEzui:password::"
        }
    ]
    
    print("🔧 Creating new task definition with AWS-native configuration...")
    print()
    print("Environment Variables:")
    for env in aws_native_env:
        if 'ENDPOINT' in env['name'] or 'HOST' in env['name']:
            print(f"  ✓ {env['name']}: {env['value']}")
    print()
    
    # Create new task definition
    container_config = {
        'name': container_def['name'],
        'image': container_def['image'],
        'portMappings': container_def['portMappings'],
        'essential': container_def['essential'],
        'environment': aws_native_env,
        'secrets': secrets,
        'logConfiguration': container_def['logConfiguration'],
        'healthCheck': container_def['healthCheck'],
    }
    
    # Only add memory/cpu if they exist in the original
    if 'cpu' in container_def and container_def['cpu'] is not None:
        container_config['cpu'] = container_def['cpu']
    if 'memory' in container_def and container_def['memory'] is not None:
        container_config['memory'] = container_def['memory']
    if 'memoryReservation' in container_def and container_def['memoryReservation'] is not None:
        container_config['memoryReservation'] = container_def['memoryReservation']
    
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def['taskRoleArn'],
        'executionRoleArn': task_def['executionRoleArn'],
        'networkMode': task_def['networkMode'],
        'containerDefinitions': [container_config],
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory'],
    }
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_revision = response['taskDefinition']['revision']
    
    print(f"✅ Created new task definition: multimodal-lib-prod-app:{new_revision}")
    print()
    
    # Update the service
    print("🚀 Updating ECS service to use new task definition...")
    service_response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=f'multimodal-lib-prod-app:{new_revision}',
        forceNewDeployment=True
    )
    
    print(f"✅ Service update initiated")
    print(f"   Deployment ID: {service_response['service']['deployments'][0]['id']}")
    print()
    
    # Save configuration summary
    summary = {
        'timestamp': datetime.now().isoformat(),
        'old_revision': 41,
        'new_revision': new_revision,
        'configuration': 'aws-native',
        'endpoints': {
            'neptune': NEPTUNE_ENDPOINT,
            'opensearch': OPENSEARCH_ENDPOINT,
            'rds': RDS_ENDPOINT,
            'redis': REDIS_ENDPOINT
        }
    }
    
    filename = f"aws-native-config-switch-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"📄 Configuration summary saved to: {filename}")
    print()
    print("=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Monitor deployment: aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    print("2. Check task logs: aws logs tail /ecs/multimodal-lib-prod-app --follow")
    print("3. Verify health: curl http://<alb-endpoint>/api/health/simple")
    print()
    print("⚠️  NOTE: You may need to update the DATABASE_PASSWORD secret ARN")
    print("   Check: aws secretsmanager list-secrets --region us-east-1 | grep multimodal")
    print()

if __name__ == '__main__':
    main()
